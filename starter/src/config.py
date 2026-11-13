"""Cau hinh chung: duong dan, tai lieu, chien luoc A/B/C."""
import os
from pathlib import Path

from dotenv import load_dotenv

STARTER_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = STARTER_DIR.parent
load_dotenv(STARTER_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

RESULTS_DIR = STARTER_DIR / "results"
BENCHMARK_FILE = ROOT_DIR / "benchmark" / "questions.json"
MANIFEST_FILE = ROOT_DIR / "data" / "manifest.csv"
EXPERIMENT_LOG = ROOT_DIR / "artifacts" / "experiment_log.csv"

# sections: (trang PDF dau, trang PDF cuoi, ten section).
# p4 "1 Slowing Growth", p17 "Spotlight", p21 "2 Structural Stasis", p35 "3 Shrinking Spaces".
DOCUMENTS = [
    {
        "document_id": "wdr2024_part1",
        "title": "World Development Report 2024: The Middle-Income Trap - Part 1 (Middle-Income Transitions)",
        "path": STARTER_DIR / "data" / "raw" / "doc1.pdf",
        "source": "data/raw/doc1.pdf",
        "url": "https://doi.org/10.1596/978-1-4648-2078-6 (trich Part 1, trang in 31-78)",
        "license": "CC BY 3.0 IGO (World Bank, ghi o trang 1 cua PDF)",
        "accessed_at": "2026-11-13",
        "skip_pages": [1],
        "sections": [
            (2, 3, "part1_overview"),
            (4, 16, "ch1_slowing_growth"),
            (17, 20, "spotlight"),
            (21, 34, "ch2_structural_stasis"),
            (35, 44, "ch3_shrinking_spaces"),
        ],
    },
]

MIN_CONTENT_CHARS = 1000

# C dung CHUNG index voi B; khac biet duy nhat la filter.
STRATEGIES = {
    "A": {"chunking": "fixed_size", "size": 500, "overlap": 50, "index": "A", "use_filter": False},
    "B": {"chunking": "by_paragraph", "max_size": 1000, "index": "B", "use_filter": False},
    "C": {"chunking": "by_paragraph", "max_size": 1000, "index": "B", "use_filter": True},
}
INDEXES = {"A": STRATEGIES["A"], "B": STRATEGIES["B"]}
TOP_K = 3