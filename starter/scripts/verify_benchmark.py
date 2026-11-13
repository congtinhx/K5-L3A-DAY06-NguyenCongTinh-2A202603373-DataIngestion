"""Kiem tra benchmark TRUOC khi chay: du so cau, du split/filter, evidence co that o trang gold.

Chay tu starter/:  python scripts/verify_benchmark.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config                                  # noqa: E402
from src.evaluation import gold_list, match_key         # noqa: E402
from src.run import load_pages                          # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

questions = json.loads(config.BENCHMARK_FILE.read_text(encoding="utf-8-sig"))
pages, _ = load_pages()
page_text = {(p.document_id, p.page): match_key(p.text) for p in pages}
sections = {p.metadata["section"] for p in pages}

problems = []
ids = [q["id"] for q in questions]
if len(ids) != len(set(ids)):
    problems.append("Trung id cau hoi")
required = ["id", "split", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote"]
for q in questions:
    missing = [k for k in required if not q.get(k)]
    if missing:
        problems.append(f"{q.get('id')}: thieu truong {missing}")
        continue
    for g in gold_list(q):
        ok = match_key(g["evidence_quote"]) in page_text.get((g["source_id"], g["page"]), "")
        print(f"{q['id']:4} {q['split']:4} p{g['page']:<3} {'OK ' if ok else 'LOI'} {g['evidence_quote'][:70]}")
        if not ok:
            problems.append(f"{q['id']}: evidence khong nam o trang {g['page']}")
    for key, value in (q.get("filter") or {}).items():
        if key == "section" and value not in sections:
            problems.append(f"{q['id']}: section '{value}' khong ton tai")

dev = [q for q in questions if q["split"] == "dev"]
test = [q for q in questions if q["split"] == "test"]
filt = [q for q in questions if q.get("filter")]
filt_test = [q for q in test if q.get("filter")]
print(f"\nTong {len(questions)} cau | dev {len(dev)} | test {len(test)} | co filter {len(filt)} (test: {len(filt_test)})")
if len(questions) < 20 or len(dev) < 15 or len(test) < 5:
    problems.append("Chua du 20 cau / 15 dev / 5 test")
if len(filt) < 3 or len(filt_test) < 1:
    problems.append("Can >= 3 cau filter, >= 1 cau filter o test")

print("\n" + ("BENCHMARK OK" if not problems else "CAN SUA:\n- " + "\n- ".join(problems)))
sys.exit(1 if problems else 0)