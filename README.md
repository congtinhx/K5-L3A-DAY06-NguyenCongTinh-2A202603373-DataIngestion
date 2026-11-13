# Day 06 – Data Ingestion – Nguyễn Công Tình (2A202603373)

Pipeline: PDF → chuẩn hóa → chunk (A/B/C) → embedding local → PostgreSQL + pgvector → benchmark Hit@1 / Evidence Hit@3 → chấm tay 3 khía cạnh.

## Cấu trúc
| Đường dẫn | Nội dung |
|---|---|
| `starter/src/` | Code pipeline: `config.py`, `ingestion.py`, `chunking.py`, `embeddings.py`, `store.py`, `evaluation.py`, `run.py` |
| `starter/scripts/` | `check_setup.py`, `verify_benchmark.py`, `show_trace.py`, `rank_of_gold.py`, `label.py` (chấm tay), `summarize_labels.py` |
| `starter/data/raw/doc1.pdf` | Corpus: WDR 2024 Part 1 (CC BY 3.0 IGO) |
| `data/manifest.csv` | Nguồn, giấy phép, số trang, quy tắc tính trang |
| `benchmark/questions.json` | 22 câu (16 dev / 6 test, 4 câu filter); `benchmark/selection_criteria.md` |
| `artifacts/experiment_log.csv` | Cấu hình, giả thuyết, kết quả A/B/C |
| `results/` (bản sao của `starter/results/`) | `ingest_stats_full_run.json`, `ingest_errors.log`, `page_stats.csv`, `reingest_check.json`, `traces_{A,B,C}.jsonl`, `summary.md/.json`, `audit_*.csv`, `manual_summary.md` |
| `report/individual/2A202603373_NguyenCongTinh.md` | Báo cáo cá nhân |

## Môi trường đã dùng
- Windows, Python 3.14, Docker Desktop
- Embedding: `intfloat/multilingual-e5-small` (sentence-transformers 6.3.0, CPU, 384 chiều, max 512 token, chi phí $0)
- Vector store: PostgreSQL 16.16 + pgvector 0.8.7 (`pgvector/pgvector:0.8.7-pg16`), cosine `<=>`, exact search
- Danh sách package: `results_pip_freeze.txt`

## Chạy lại (Windows CMD, từ thư mục `starter`)
```cmd
python -m venv ..\.venv
..\.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
REM trong .env đặt: EMBEDDING_MODEL=intfloat/multilingual-e5-small
docker compose -p day6_student_starter up -d --wait
python scripts\check_setup.py
python scripts\verify_benchmark.py
python -m src.run ingest
python -m src.run evaluate
python -m src.run reingest-check
```
Xem trace: `python scripts\show_trace.py q14 t04`. Chấm tay: `python scripts\label.py coherence|metadata|grounding`, tổng hợp: `python scripts\summarize_labels.py`.

Đề bài gốc: xem lịch sử Git của file này hoặc `GUIDE.md`, `BENCHMARK.md`, `RUBRIC.md`.
