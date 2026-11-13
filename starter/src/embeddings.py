"""Embedding model that chay local bang Sentence Transformers."""
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, question: str) -> list[float]: ...


class MyEmbedder:
    """Boc SentenceTransformer. Khong co fallback sang vector gia: loi thi dung.

    Model ho E5 can tien to "query: " cho cau hoi va "passage: " cho tai lieu.
    Vector duoc chuan hoa do dai 1 de dung cosine.
    """

    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        from sentence_transformers import SentenceTransformer

        if not model_name:
            raise ValueError("EMBEDDING_MODEL chua duoc dat trong .env")
        self.model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device="cpu")
        dim_fn = getattr(self.model, "get_embedding_dimension", None) or self.model.get_sentence_embedding_dimension
        self.dimensions = int(dim_fn())
        self.max_seq_length = int(self.model.max_seq_length)
        is_e5 = "e5" in model_name.lower()
        self.query_prefix = "query: " if is_e5 else ""
        self.doc_prefix = "passage: " if is_e5 else ""

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                    show_progress_bar=len(texts) > 64, convert_to_numpy=True)
        if len(vectors) != len(texts) or vectors.shape[1] != self.dimensions:
            raise RuntimeError("So vector hoac so chieu khong khop")
        return vectors.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self.doc_prefix + t for t in texts]) if texts else []

    def embed_query(self, question: str) -> list[float]:
        return self._encode([self.query_prefix + question])[0]

    def describe(self) -> dict:
        return {"provider": "local sentence-transformers", "model": self.model_name,
                "dimensions": self.dimensions, "max_seq_length": self.max_seq_length,
                "query_prefix": self.query_prefix, "doc_prefix": self.doc_prefix,
                "normalized": True, "device": "cpu"}