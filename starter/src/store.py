"""Luu va tim vector bang PostgreSQL + pgvector (cosine, exact search)."""
import hashlib
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .models import Chunk

ALLOWED_FILTERS = {"section", "document_id", "page"}


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def to_vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vector) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL trong .env dang trong")
        if dimensions <= 0:
            raise ValueError("dimensions phai > 0")
        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, connect_timeout=5)

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id      TEXT PRIMARY KEY,
                    strategy      TEXT NOT NULL,
                    document_id   TEXT NOT NULL,
                    source        TEXT NOT NULL,
                    page          INTEGER NOT NULL,
                    printed_page  INTEGER,
                    section       TEXT,
                    char_start    INTEGER,
                    char_end      INTEGER,
                    text          TEXT NOT NULL,
                    content_hash  TEXT NOT NULL,
                    model_name    TEXT NOT NULL,
                    embedding     vector({dim}) NOT NULL,
                    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
                )""").format(dim=sql.Literal(self.dimensions)))
            conn.execute("CREATE INDEX IF NOT EXISTS chunks_strategy_section_idx ON chunks (strategy, section)")
            row = conn.execute("""
                SELECT format_type(atttypid, atttypmod) FROM pg_attribute
                WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'""").fetchone()
            if row[0] != f"vector({self.dimensions})":
                raise RuntimeError(f"Bang chunks dang dung {row[0]}, model hien tai {self.dimensions} chieu. "
                                   "Doi model thi phai xoa bang: DROP TABLE chunks;")

    def existing_hashes(self, strategy: str, document_id: str, model_name: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chunk_id, content_hash FROM chunks WHERE strategy=%s AND document_id=%s AND model_name=%s",
                (strategy, document_id, model_name)).fetchall()
        return dict(rows)

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]],
               model_name: str, document_id: str, keep_ids: set[str]) -> dict[str, int]:
        """Ghi chunk moi/doi theo chunk_id on dinh (khong nhan doi) va xoa chunk cu khong con."""
        if len(chunks) != len(vectors):
            raise ValueError("So chunk va so vector khac nhau")
        for v in vectors:
            if len(v) != self.dimensions:
                raise ValueError(f"Vector {len(v)} chieu, can {self.dimensions}")
        rows = [(c.chunk_id, strategy, c.document_id, c.source, c.page,
                 c.metadata.get("printed_page"), c.metadata.get("section"),
                 c.metadata.get("char_start"), c.metadata.get("char_end"),
                 c.text, content_hash(c.text), model_name, to_vector_literal(v))
                for c, v in zip(chunks, vectors)]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany("""
                    INSERT INTO chunks (chunk_id, strategy, document_id, source, page, printed_page, section,
                                        char_start, char_end, text, content_hash, model_name, embedding)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        strategy=EXCLUDED.strategy, document_id=EXCLUDED.document_id, source=EXCLUDED.source,
                        page=EXCLUDED.page, printed_page=EXCLUDED.printed_page, section=EXCLUDED.section,
                        char_start=EXCLUDED.char_start, char_end=EXCLUDED.char_end, text=EXCLUDED.text,
                        content_hash=EXCLUDED.content_hash, model_name=EXCLUDED.model_name,
                        embedding=EXCLUDED.embedding, ingested_at=now()""", rows)
                cur.execute("""DELETE FROM chunks WHERE strategy=%s AND document_id=%s
                               AND NOT (chunk_id = ANY(%s))""", (strategy, document_id, list(keep_ids)))
                deleted = cur.rowcount
        return {"written": len(rows), "deleted_obsolete": deleted}

    def count(self, strategy: str | None = None) -> int:
        with self._connect() as conn:
            if strategy:
                return conn.execute("SELECT count(*) FROM chunks WHERE strategy=%s", (strategy,)).fetchone()[0]
            return conn.execute("SELECT count(*) FROM chunks").fetchone()[0]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Loc metadata trong SQL roi xep hang theo cosine distance (<=>)."""
        if len(query_vector) != self.dimensions:
            raise ValueError("Query vector sai so chieu")
        conditions = [sql.SQL("strategy = %(strategy)s")]
        params: dict[str, Any] = {"strategy": strategy, "q": to_vector_literal(query_vector), "k": top_k}
        for i, (key, value) in enumerate((filters or {}).items()):
            if key not in ALLOWED_FILTERS:
                raise ValueError(f"Khong cho phep loc theo {key!r}")
            conditions.append(sql.SQL("{} = %({})s").format(sql.Identifier(key), sql.SQL(f"f{i}")))
            params[f"f{i}"] = value
        query = sql.SQL("""
            SELECT chunk_id, document_id, source, page, printed_page, section, char_start, char_end, text,
                   1 - (embedding <=> %(q)s::vector) AS score
            FROM chunks WHERE {where}
            ORDER BY embedding <=> %(q)s::vector
            LIMIT %(k)s""").format(where=sql.SQL(" AND ").join(conditions))
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                return [dict(r) | {"score": float(r["score"])} for r in cur.fetchall()]