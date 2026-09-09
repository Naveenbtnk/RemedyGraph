"""Local embedding contracts, a deterministic test encoder, and vector search."""

from __future__ import annotations

import hashlib
import importlib
import math
import re
from collections.abc import Sequence
from typing import Protocol, cast

from backend.app.rag.contracts import DocumentChunk, RetrievalSource, SearchResult

_TOKEN = re.compile(r"[A-Za-z0-9_]+")


class EmbeddingEncoder(Protocol):
    @property
    def dimension(self) -> int: ...

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class DeterministicFakeEncoder:
    """Network-free hashed bag-of-words encoder for deterministic tests."""

    def __init__(self, dimension: int = 64) -> None:
        if dimension < 8:
            raise ValueError("embedding dimension must be at least 8")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode_one(text) for text in texts]

    def _encode_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class _SentenceTransformerModel(Protocol):
    def encode(
        self, texts: list[str], *, normalize_embeddings: bool, show_progress_bar: bool
    ) -> object: ...

    def get_sentence_embedding_dimension(self) -> int | None: ...


class SentenceTransformerEncoder:
    """Optional sentence-transformers adapter that is local-files-only by default."""

    def __init__(
        self,
        model_name_or_path: str,
        *,
        local_files_only: bool = True,
    ) -> None:
        try:
            module = importlib.import_module("sentence_transformers")
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers support is not installed; install the 'embeddings' extra"
            ) from exc
        model_class = getattr(module, "SentenceTransformer", None)
        if model_class is None:
            raise RuntimeError("sentence_transformers has no SentenceTransformer class")
        self._model = cast(
            _SentenceTransformerModel,
            model_class(model_name_or_path, local_files_only=local_files_only),
        )
        dimension = self._model.get_sentence_embedding_dimension()
        if dimension is None:
            raise RuntimeError("embedding model did not report a dimension")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        encoded = self._model.encode(
            list(texts), normalize_embeddings=True, show_progress_bar=False
        )
        if hasattr(encoded, "tolist"):
            encoded = encoded.tolist()
        return [[float(value) for value in row] for row in cast(Sequence[Sequence[float]], encoded)]


class SemanticIndex:
    """Small in-process vector index appropriate for the local MVP."""

    def __init__(self, encoder: EmbeddingEncoder) -> None:
        self.encoder = encoder
        self._chunks: dict[str, DocumentChunk] = {}
        self._vectors: dict[str, list[float]] = {}

    def index(self, chunks: Sequence[DocumentChunk]) -> None:
        vectors = self.encoder.encode([chunk.text for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("encoder returned the wrong number of vectors")
        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != self.encoder.dimension:
                raise ValueError("encoder returned a vector with the wrong dimension")
            self._chunks[chunk.id] = chunk
            self._vectors[chunk.id] = vector

    def search(self, query: str, *, limit: int = 20) -> list[SearchResult]:
        if limit <= 0 or not query.strip() or not self._chunks:
            return []
        query_vectors = self.encoder.encode([query])
        if len(query_vectors) != 1 or len(query_vectors[0]) != self.encoder.dimension:
            raise ValueError("encoder returned an invalid query vector")
        query_vector = query_vectors[0]
        scored = [
            (chunk_id, sum(left * right for left, right in zip(query_vector, vector, strict=True)))
            for chunk_id, vector in self._vectors.items()
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [
            SearchResult(
                chunk=self._chunks[chunk_id],
                source=RetrievalSource.SEMANTIC,
                rank=rank,
                score=score,
            )
            for rank, (chunk_id, score) in enumerate(scored[:limit], start=1)
        ]
