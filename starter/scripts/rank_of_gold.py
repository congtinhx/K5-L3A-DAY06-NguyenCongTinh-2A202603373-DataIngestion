"""Tim hang cua chunk dung (status=hit) trong top-30. Vi du: python scripts\\rank_of_gold.py B q14 t04"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config                              # noqa: E402
from src.evaluation import hit_status               # noqa: E402
from src.run import get_embedder_and_store          # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
strategy, ids = sys.argv[1], set(sys.argv[2:])
questions = [q for q in json.loads(config.BENCHMARK_FILE.read_text(encoding="utf-8-sig")) if q["id"] in ids]
embedder, store = get_embedder_and_store()
for q in questions:
    hits = store.search(config.STRATEGIES[strategy]["index"], embedder.embed_query(q["question"]), 30)
    ranks = [(i + 1, h) for i, h in enumerate(hits) if hit_status(q, h) == "hit"]
    if ranks:
        r, h = ranks[0]
        print(f"{strategy} {q['id']}: chunk dung o hang {r} (score={h['score']:.3f}, dai {len(h['text'])} ky tu)")
        print(f"   {h['chunk_id']}: {h['text'][:250]}")
    else:
        print(f"{strategy} {q['id']}: khong co chunk dung trong top-30")