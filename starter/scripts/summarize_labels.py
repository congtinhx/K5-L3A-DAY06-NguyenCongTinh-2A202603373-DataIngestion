"""Tổng hợp nhãn chấm tay trong results/audit_*.csv -> results/manual_summary.md

Chạy từ starter/ SAU KHI đã điền các cột điểm:  python scripts/summarize_labels.py
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def read(name: str) -> list[dict]:
    with (RESULTS / name).open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def scores(rows: list[dict], column: str, allowed: set[str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        value = r[column].strip()
        if value not in allowed:
            raise SystemExit(f"{column} chua dien/khong hop le o dong: {r.get('id') or r.get('position_id')} "
                             f"strategy {r['strategy']} (gia tri '{value}')")
        out[r["strategy"]].append(int(value))
    return out


coh = scores(read("audit_coherence.csv"), "coherence_0_1_2", {"0", "1", "2"})
meta_rows = read("audit_metadata.csv")
meta = scores(meta_rows, "metadata_correct_0_1", {"0", "1"})
ground = scores(read("audit_grounding.csv"), "grounding_0_1_2", {"0", "1", "2"})

filter_q = defaultdict(dict)
for r in meta_rows:
    if r["filter_ok_auto"] != "":
        filter_q[r["strategy"]][r["id"]] = r["filter_ok_auto"] == "True"

lines = ["| Strategy | Coherence TB /2 (n) | Metadata du va dung (n/N) | Filter tuan thu (n/N) | "
         "Grounding 0/1/2 (so cau) | Grounding TB /2 |", "|---|---|---|---|---|---|"]
for s in sorted(coh):
    c, m, g = coh[s], meta[s], ground[s]
    dist = Counter(g)
    fq = filter_q.get(s, {})
    fstr = f"{sum(fq.values())}/{len(fq)}" if fq else "N/A"
    lines.append(f"| {s} | {sum(c)/len(c):.2f} ({len(c)}) | {sum(m)}/{len(m)} | {fstr} | "
                 f"{dist[0]}/{dist[1]}/{dist[2]} | {sum(g)/len(g):.2f} |")
text = "\n".join(lines) + "\n"
(RESULTS / "manual_summary.md").write_text(text, encoding="utf-8")
print(text)
