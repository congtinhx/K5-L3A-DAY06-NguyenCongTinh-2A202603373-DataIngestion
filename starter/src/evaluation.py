"""Cham Hit@1 / Evidence Hit@3 tu dong va giu trace tung cau hoi."""
import unicodedata
from collections import defaultdict
from typing import Any


def match_key(text: str) -> str:
    """Chi giu chu va so (chu thuong) de so evidence, bo qua loi khoang trang/gach noi cua PDF."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).lower() if ch.isalnum())


def gold_list(question: dict[str, Any]) -> list[dict[str, Any]]:
    golds = [{"source_id": question["gold_source_id"], "page": question["gold_page"],
              "evidence_quote": question["evidence_quote"]}]
    golds += question.get("alt_gold", [])
    return golds


def hit_status(question: dict[str, Any], hit: dict[str, Any]) -> str:
    """'hit' = dung nguon/trang va chua DU evidence; 'page_only' = dung trang nhung thieu evidence; 'miss'."""
    status = "miss"
    text_key = match_key(hit["text"])
    for g in gold_list(question):
        if hit["document_id"] == g["source_id"] and hit["page"] == g["page"]:
            if match_key(g["evidence_quote"]) in text_key:
                return "hit"
            status = "page_only"
    return status


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]],
                   strategy: str, applied_filter: dict[str, Any] | None) -> dict[str, Any]:
    statuses = [hit_status(question, h) for h in hits]
    wanted = question.get("filter") or None
    filter_ok = None
    if wanted:
        filter_ok = all(all(h.get(k) == v for k, v in wanted.items()) for h in hits)
    return {
        "strategy": strategy,
        "id": question["id"],
        "split": question["split"],
        "type": question.get("type"),
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "gold": gold_list(question),
        "question_filter": wanted,
        "applied_filter": applied_filter,
        "hit_at_1": bool(statuses) and statuses[0] == "hit",
        "hit_at_3": "hit" in statuses,
        "first_hit_rank": statuses.index("hit") + 1 if "hit" in statuses else None,
        "evidence_split_suspected": "hit" not in statuses and "page_only" in statuses,
        "filter_respected": filter_ok,
        "hits": [
            {"rank": i + 1, "status": s, **{k: h[k] for k in
             ("chunk_id", "score", "document_id", "source", "page", "printed_page", "section", "text")}}
            for i, (h, s) in enumerate(zip(hits, statuses))
        ],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Gom theo (strategy, split): Hit@1, Hit@3, tuan thu filter, luon kem n/N."""
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for t in traces:
        groups[(t["strategy"], t["split"])].append(t)
    out: dict[str, Any] = {}
    for (strategy, split), items in sorted(groups.items()):
        n = len(items)
        h1 = sum(t["hit_at_1"] for t in items)
        h3 = sum(t["hit_at_3"] for t in items)
        filt = [t for t in items if t["question_filter"]]
        fok = sum(bool(t["filter_respected"]) for t in filt)
        out.setdefault(strategy, {})[split] = {
            "N": n, "hit1": h1, "hit3": h3,
            "hit1_str": f"{h1}/{n}", "hit3_str": f"{h3}/{n}",
            "hit1_rate": round(h1 / n, 3) if n else None,
            "hit3_rate": round(h3 / n, 3) if n else None,
            "filter_respected_str": f"{fok}/{len(filt)}" if filt else "N/A",
            "evidence_split_suspected": [t["id"] for t in items if t["evidence_split_suspected"]],
            "missed_ids": [t["id"] for t in items if not t["hit_at_3"]],
        }
    return out