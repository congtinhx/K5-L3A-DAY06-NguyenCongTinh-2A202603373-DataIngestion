"""Pipeline Day 06. Chay tu thu muc starter/:

    python -m src.run ingest          # doc PDF, chunk A/B, embed, luu pgvector, ghi manifest + thong ke
    python -m src.run reingest-check  # nap lai lan nua, chung minh khong nhan doi
    python -m src.run evaluate        # chay benchmark A/B/C, ghi trace + summary + bang cham tay
    python -m src.run all             # ingest roi evaluate
"""
import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .chunking import by_paragraph, fixed_size
from .evaluation import evaluate_query, summarize
from .ingestion import load_pdf
from .models import Chunk, DocumentPage


# ---------------------------------------------------------------- tien ich
def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_pages() -> tuple[list[DocumentPage], list[str]]:
    pages, errors = [], []
    for d in config.DOCUMENTS:
        pages += load_pdf(d["path"], d["document_id"], d["source"], d["sections"], d["skip_pages"], errors)
    return pages, errors


def build_chunks(index: str, pages: list[DocumentPage]) -> list[Chunk]:
    cfg = config.INDEXES[index]
    if cfg["chunking"] == "fixed_size":
        return [c for p in pages for c in fixed_size(p, cfg["size"], cfg["overlap"], prefix=index)]
    return [c for p in pages for c in by_paragraph(p, cfg["max_size"], prefix=index)]


def length_stats(chunks: list[Chunk]) -> dict:
    lengths = [len(c.text) for c in chunks]
    return {"chunk_count": len(lengths), "min_chars": min(lengths), "median_chars": statistics.median(lengths),
            "mean_chars": round(statistics.mean(lengths), 1), "max_chars": max(lengths),
            "total_chars": sum(lengths)}


def get_embedder_and_store():
    from .embeddings import MyEmbedder
    from .store import PgVectorStore
    embedder = MyEmbedder(config.EMBEDDING_MODEL)
    store = PgVectorStore(config.DATABASE_URL, embedder.dimensions)
    store.create_schema()
    return embedder, store


# ---------------------------------------------------------------- ingest
def write_manifest(pages: list[DocumentPage]) -> dict:
    from pypdf import PdfReader
    page_rows, manifest_rows, counted_total = [], [], 0
    for d in config.DOCUMENTS:
        physical = len(PdfReader(str(d["path"])).pages)
        doc_pages = [p for p in pages if p.document_id == d["document_id"]]
        counted = [p.page for p in doc_pages if p.metadata["chars"] >= config.MIN_CONTENT_CHARS]
        counted_total += len(counted)
        for p in doc_pages:
            page_rows.append({"document_id": p.document_id, "pdf_page": p.page,
                              "printed_page": p.metadata["printed_page"], "section": p.metadata["section"],
                              "raw_chars": p.metadata["raw_chars"], "normalized_chars": p.metadata["chars"],
                              "notes_removed": p.metadata["notes_removed"],
                              "counted_as_content": p.page in counted})
        manifest_rows.append({
            "source_id": d["document_id"], "title": d["title"], "source_path_or_url": f'{d["source"]} | {d["url"]}',
            "license_or_permission": d["license"], "accessed_at": d["accessed_at"],
            "physical_pages": physical, "ingested_pages": len(doc_pages),
            "counted_content_pages": len(counted), "counted_page_ids": " ".join(map(str, counted)),
            "skipped_pages": " ".join(map(str, d["skip_pages"])),
            "counting_rule": f">= {config.MIN_CONTENT_CHARS} ky tu sau chuan hoa va cat Notes/References",
            "total_normalized_chars": sum(p.metadata["chars"] for p in doc_pages),
        })
    write_csv(config.MANIFEST_FILE, manifest_rows)
    write_csv(config.RESULTS_DIR / "page_stats.csv", page_rows)
    return {"counted_content_pages": counted_total}


def ingest() -> dict:
    from .store import content_hash
    t0 = time.perf_counter()
    pages, errors = load_pages()
    read_seconds = time.perf_counter() - t0
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.RESULTS_DIR / "ingest_errors.log").write_text("\n".join(errors) + "\n", encoding="utf-8")
    counts = write_manifest(pages)
    if counts["counted_content_pages"] < 30:
        raise SystemExit(f"Chi co {counts['counted_content_pages']} trang noi dung (< 30). Bo sung tai lieu.")
    print(f"Doc {len(pages)} trang, {counts['counted_content_pages']} trang noi dung, {len(errors)} ghi chu loi.")

    embedder, store = get_embedder_and_store()
    stats = {"run_at": now_iso(), "embedder": embedder.describe(), "read_seconds": round(read_seconds, 2),
             "vector_store": "PostgreSQL 16 + pgvector 0.8.7 (docker image pgvector/pgvector:0.8.7-pg16)",
             "metric": "cosine (<=>), exact search (khong dung index ANN)", "cost_usd": 0, "indexes": {}}
    for index in config.INDEXES:
        t1 = time.perf_counter()
        chunks = build_chunks(index, pages)
        chunk_seconds = time.perf_counter() - t1
        written = deleted = embedded = 0
        t2 = time.perf_counter()
        for d in config.DOCUMENTS:
            doc_chunks = [c for c in chunks if c.document_id == d["document_id"]]
            old = store.existing_hashes(index, d["document_id"], embedder.model_name)
            todo = [c for c in doc_chunks if old.get(c.chunk_id) != content_hash(c.text)]
            vectors = embedder.embed_documents([c.text for c in todo])
            embedded += len(todo)
            res = store.upsert(index, todo, vectors, embedder.model_name, d["document_id"],
                               {c.chunk_id for c in doc_chunks})
            written += res["written"]
            deleted += res["deleted_obsolete"]
        stats["indexes"][index] = {**length_stats(chunks), "config": config.INDEXES[index],
                                   "chunk_seconds": round(chunk_seconds, 2),
                                   "embed_and_store_seconds": round(time.perf_counter() - t2, 2),
                                   "embedded_now": embedded, "written": written, "deleted_obsolete": deleted,
                                   "rows_in_db": store.count(index)}
        print(f"Index {index}: {len(chunks)} chunk, embed moi {embedded}, xoa cu {deleted}, "
              f"trong DB {stats['indexes'][index]['rows_in_db']}")
    stats["total_seconds"] = round(time.perf_counter() - t0, 2)
    write_json(config.RESULTS_DIR / "ingest_stats.json", stats)
    return stats


def reingest_check() -> None:
    _, store = get_embedder_and_store()
    before = {i: store.count(i) for i in config.INDEXES}
    stats = ingest()
    after = {i: store.count(i) for i in config.INDEXES}
    result = {"run_at": now_iso(), "before": before, "after": after,
              "embedded_on_rerun": {i: stats["indexes"][i]["embedded_now"] for i in config.INDEXES},
              "no_duplicates": before == after}
    write_json(config.RESULTS_DIR / "reingest_check.json", result)
    print(json.dumps(result, indent=2))


# ---------------------------------------------------------------- evaluate
def load_questions() -> list[dict]:
    questions = json.loads(config.BENCHMARK_FILE.read_text(encoding="utf-8-sig"))
    dev = sum(q["split"] == "dev" for q in questions)
    test = sum(q["split"] == "test" for q in questions)
    if len(questions) < 20 or dev < 15 or test < 5:
        raise SystemExit(f"Benchmark chua du: {len(questions)} cau, dev={dev}, test={test}")
    return questions


def evaluate() -> None:
    questions = load_questions()
    embedder, store = get_embedder_and_store()
    traces = []
    query_vectors = {q["id"]: embedder.embed_query(q["question"]) for q in questions}
    for strategy, cfg in config.STRATEGIES.items():
        t0 = time.perf_counter()
        for q in questions:
            applied = q.get("filter") if cfg["use_filter"] and q.get("filter") else None
            hits = store.search(cfg["index"], query_vectors[q["id"]], config.TOP_K, applied)
            traces.append(evaluate_query(q, hits, strategy, applied))
        print(f"Strategy {strategy}: {len(questions)} cau, {time.perf_counter() - t0:.2f}s")
    out = config.RESULTS_DIR
    for strategy in config.STRATEGIES:
        with (out / f"traces_{strategy}.jsonl").open("w", encoding="utf-8") as f:
            for t in traces:
                if t["strategy"] == strategy:
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
    summary = summarize(traces)
    write_json(out / "summary.json", {"run_at": now_iso(), "model": embedder.model_name, "top_k": config.TOP_K,
                                      "strategies": config.STRATEGIES, "results": summary})
    write_summary_markdown(summary)
    update_experiment_log(summary)
    write_audit_sheets(traces)
    print((out / "summary.md").read_text(encoding="utf-8"))


def write_summary_markdown(summary: dict) -> None:
    ingest_stats = json.loads((config.RESULTS_DIR / "ingest_stats.json").read_text(encoding="utf-8"))
    lines = ["| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Filter tuan thu | Chunk count | "
             "Embed+store (s) | Chi phi |", "|---|---|---|---|---|---|---|---|"]
    for strategy, cfg in config.STRATEGIES.items():
        idx = ingest_stats["indexes"][cfg["index"]]
        for split in ("dev", "test"):
            r = summary[strategy][split]
            lines.append(f"| {strategy} | {split} | {r['hit1_str']} | {r['hit3_str']} | {r['filter_respected_str']} "
                         f"| {idx['chunk_count']} | {idx['embed_and_store_seconds']} | $0 |")
    lines += ["", "Cau truot Hit@3 (dev/test):"]
    for strategy in config.STRATEGIES:
        lines.append(f"- {strategy}: dev {summary[strategy]['dev']['missed_ids']} | "
                     f"test {summary[strategy]['test']['missed_ids']}")
    (config.RESULTS_DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_experiment_log(summary: dict) -> None:
    """Dien cot so lieu; giu nguyen cot hypothesis/notes ban viet tay."""
    path = config.EXPERIMENT_LOG
    old = {}
    if path.exists():
        with path.open(encoding="utf-8-sig") as f:
            old = {r["strategy"]: r for r in csv.DictReader(f)}
    rows = []
    for strategy, cfg in config.STRATEGIES.items():
        prev = old.get(strategy, {})
        rows.append({
            "strategy": strategy, "chunking": cfg["chunking"],
            "chunk_size": cfg.get("size", cfg.get("max_size")), "overlap": cfg.get("overlap", 0),
            "metadata": "document_id,source,page,printed_page,section,char_start,char_end",
            "filter": "section (chi khi cau hoi co filter)" if cfg["use_filter"] else "none",
            "vectorizer": config.EMBEDDING_MODEL, "hypothesis": prev.get("hypothesis", ""),
            "dev_hit1": summary[strategy]["dev"]["hit1_str"], "dev_hit3": summary[strategy]["dev"]["hit3_str"],
            "test_hit1": summary[strategy]["test"]["hit1_str"], "test_hit3": summary[strategy]["test"]["hit3_str"],
            "notes": prev.get("notes", ""),
        })
    write_csv(path, rows)


def write_audit_sheets(traces: list[dict]) -> None:
    """Tao 3 bang de ban cham tay (cot trong = ban dien)."""
    out = config.RESULTS_DIR
    test = [t for t in traces if t["split"] == "test"]

    meta_rows = [{"strategy": t["strategy"], "id": t["id"], "rank": h["rank"], "chunk_id": h["chunk_id"],
                  "source": h["source"], "pdf_page": h["page"], "printed_page": h["printed_page"],
                  "section": h["section"], "question_filter": json.dumps(t["question_filter"]),
                  "filter_ok_auto": "" if t["filter_respected"] is None else t["filter_respected"],
                  "text_preview": h["text"][:160],
                  "metadata_correct_0_1": "", "error_note": ""}
                 for t in test for h in t["hits"]]
    write_csv(out / "audit_metadata.csv", meta_rows)

    ground_rows = [{"strategy": t["strategy"], "id": t["id"], "question": t["question"],
                    "expected_answer": t["expected_answer"], "evidence_hit3_auto": t["hit_at_3"],
                    "top1": t["hits"][0]["text"] if t["hits"] else "",
                    "top2": t["hits"][1]["text"] if len(t["hits"]) > 1 else "",
                    "top3": t["hits"][2]["text"] if len(t["hits"]) > 2 else "",
                    "grounding_0_1_2": "", "reason": ""} for t in test]
    write_csv(out / "audit_grounding.csv", ground_rows)

    # Coherence: 10 vi tri co dinh = diem giua cua 10 trang noi dung dau tien (chon TRUOC khi xem diem)
    pages, _ = load_pages()
    targets = [p for p in pages if p.metadata["chars"] >= config.MIN_CONTENT_CHARS][:10]
    chunks = {i: build_chunks(i, targets) for i in config.INDEXES}
    coh_rows = []
    for n, p in enumerate(targets, start=1):
        pos = len(p.text) // 2
        for strategy, cfg in config.STRATEGIES.items():
            same_page = [c for c in chunks[cfg["index"]] if c.page == p.page and c.document_id == p.document_id]
            c = min(same_page, key=lambda c: 0 if c.metadata["char_start"] <= pos < c.metadata["char_end"]
                    else min(abs(pos - c.metadata["char_start"]), abs(pos - c.metadata["char_end"])))
            coh_rows.append({"position_id": f"pos{n:02d}", "pdf_page": p.page, "char_pos": pos,
                             "strategy": strategy, "chunk_id": c.chunk_id,
                             "note": "C dung chung chunk voi B" if strategy == "C" else "",
                             "chunk_text": c.text, "coherence_0_1_2": "", "reason": ""})
    write_csv(out / "audit_coherence.csv", coh_rows)


# ---------------------------------------------------------------- main
def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Day 06 data ingestion pipeline")
    parser.add_argument("command", choices=["ingest", "reingest-check", "evaluate", "all"])
    args = parser.parse_args()
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if args.command == "ingest":
        ingest()
    elif args.command == "reingest-check":
        reingest_check()
    elif args.command == "evaluate":
        evaluate()
    else:
        ingest()
        evaluate()


if __name__ == "__main__":
    main()