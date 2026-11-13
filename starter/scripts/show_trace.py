"""Xem chi tiet top-3 cua mot so cau hoi. Vi du: python scripts\\show_trace.py q14 t04"""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ids = set(sys.argv[1:])
results = Path(__file__).resolve().parents[1] / "results"
for s in "ABC":
    for line in open(results / f"traces_{s}.jsonl", encoding="utf-8"):
        t = json.loads(line)
        if t["id"] not in ids:
            continue
        print(f"=== Strategy {s} | {t['id']} ({t['split']}) | Hit@1={t['hit_at_1']} Hit@3={t['hit_at_3']} "
              f"| filter={t['applied_filter']}")
        print("Cau hoi :", t["question"])
        print("Gold    : trang", [g["page"] for g in t["gold"]], "|", t["gold"][0]["evidence_quote"])
        for h in t["hits"]:
            print(f"  #{h['rank']} trang {h['page']} | {h['section']} | {h['status']} | score={h['score']:.3f}")
            print(f"     {h['text'][:300]}")
        print()