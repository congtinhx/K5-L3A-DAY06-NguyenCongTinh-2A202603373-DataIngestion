"""Cham tay ngay trong terminal. Chay tu starter/:

    python scripts\\label.py coherence
    python scripts\\label.py metadata
    python scripts\\label.py grounding

Moi dong: go diem roi Enter, go ly do roi Enter. Go s = bo qua, q = luu va thoat.
Luu sau moi dong, chay lai se tiep tuc tu dong chua cham.
"""
import csv
import sys
import textwrap
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
RESULTS = Path(__file__).resolve().parents[1] / "results"

SHEETS = {
    "coherence": {
        "file": "audit_coherence.csv", "score": "coherence_0_1_2", "reason": "reason", "allowed": {"0", "1", "2"},
        "guide": "0 = cat cut/kho hieu | 1 = hieu mot phan, thieu ngu canh | 2 = tron y, doc rieng van hieu",
        "show": lambda r: f"[{r['position_id']}] trang PDF {r['pdf_page']} | strategy {r['strategy']} | {r['chunk_id']}\n"
                          f"--- CHUNK ---\n{wrap(r['chunk_text'])}",
        "share_key": lambda r: r["chunk_id"],
    },
    "metadata": {
        "file": "audit_metadata.csv", "score": "metadata_correct_0_1", "reason": "error_note", "allowed": {"0", "1"},
        "guide": "Mo PDF dung trang PDF ben duoi: doan chu co nam o trang do va dung chuong (section) khong? "
                 "1 = du va dung | 0 = sai/thieu",
        "show": lambda r: f"[{r['id']} | {r['strategy']} | hang {r['rank']}] {r['chunk_id']}\n"
                          f"source={r['source']} | trang PDF={r['pdf_page']} | trang in={r['printed_page']} | "
                          f"section={r['section']} | filter cau hoi={r['question_filter']} | filter_ok_auto={r['filter_ok_auto']}\n"
                          f"--- DOAN DAU CHUNK ---\n{wrap(r['text_preview'])}",
        "share_key": lambda r: r["chunk_id"],
    },
    "grounding": {
        "file": "audit_grounding.csv", "score": "grounding_0_1_2", "reason": "reason", "allowed": {"0", "1", "2"},
        "guide": "Chi doc 3 chunk duoi day: 0 = khong co bang chung | 1 = co mot phan/thieu dieu kien | "
                 "2 = du de tra loi va truy nguon",
        "show": lambda r: f"[{r['id']} | strategy {r['strategy']}] Evidence Hit@3 tu dong = {r['evidence_hit3_auto']}\n"
                          f"CAU HOI : {r['question']}\nDAP AN  : {r['expected_answer']}\n"
                          f"--- TOP 1 ---\n{wrap(r['top1'])}\n--- TOP 2 ---\n{wrap(r['top2'])}\n"
                          f"--- TOP 3 ---\n{wrap(r['top3'])}",
        "share_key": None,
    },
}


def wrap(text: str) -> str:
    return "\n".join(textwrap.wrap(text, 110)) or "(trong)"


def save(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in SHEETS:
        raise SystemExit("Dung: python scripts\\label.py coherence|metadata|grounding")
    cfg = SHEETS[sys.argv[1]]
    path = RESULTS / cfg["file"]
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    score, reason = cfg["score"], cfg["reason"]

    def propagate(row: dict) -> int:
        """Chunk giong het (cung chunk_id) thi dung chung nhan."""
        if not cfg["share_key"]:
            return 0
        n = 0
        for other in rows:
            if other is not row and not other[score].strip() and cfg["share_key"](other) == cfg["share_key"](row):
                other[score] = row[score]
                other[reason] = f"(cung chunk) {row[reason]}"
                n += 1
        return n

    todo = [r for r in rows if not r[score].strip()]
    print(f"{path.name}: {len(rows)} dong, con {len(todo)} dong chua cham.\nThang diem: {cfg['guide']}\n")
    for r in rows:
        if r[score].strip():
            continue
        print("=" * 110)
        print(cfg["show"](r))
        print("-" * 110)
        while True:
            value = input(f"Diem {sorted(cfg['allowed'])} (s=bo qua, q=thoat): ").strip().lower()
            if value in cfg["allowed"] | {"s", "q"}:
                break
        if value == "q":
            break
        if value == "s":
            continue
        r[score] = value
        r[reason] = input("Ly do (ngan gon): ").strip()
        copied = propagate(r)
        save(path, rows)
        if copied:
            print(f"  -> da dien tu dong cho {copied} dong khac dung chung chunk nay")
    save(path, rows)
    left = sum(1 for r in rows if not r[score].strip())
    print(f"\nDa luu {path.name}. Con {left} dong chua cham.")


if __name__ == "__main__":
    main()