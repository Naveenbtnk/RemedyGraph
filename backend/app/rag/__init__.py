"""Local repository ingestion and retrieval primitives."""

from backend.app.rag.contracts import (
    DocumentChunk,
    EvidenceCandidate,
    NormalizedDocument,
    SearchResult,
)

__all__ = ["DocumentChunk", "EvidenceCandidate", "NormalizedDocument", "SearchResult"]
