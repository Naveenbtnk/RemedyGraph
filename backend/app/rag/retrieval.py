"""Deterministic hybrid merging, reranking, top-k selection, and retrieval logging."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Sequence

from backend.app.rag.contracts import (
    EvidenceCandidate,
    RetrievalCandidateLog,
    RetrievalLogEntry,
    SearchResult,
)
from backend.app.rag.embeddings import SemanticIndex
from backend.app.rag.index import LexicalIndex
from backend.app.rag.redaction import redact_text

_TERM = re.compile(r"[A-Za-z0-9_]+")


class RetrievalLogger:
    """Emit structured events and retain a bounded in-memory view for run persistence."""

    def __init__(self, *, max_entries: int = 1_000) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self.entries: list[RetrievalLogEntry] = []
        self._logger = logging.getLogger("remedygraph.retrieval")

    def record(self, entry: RetrievalLogEntry) -> None:
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            del self.entries[: len(self.entries) - self.max_entries]
        self._logger.info("retrieval %s", json.dumps(entry.model_dump(mode="json"), sort_keys=True))


class HybridRetriever:
    def __init__(
        self,
        lexical: LexicalIndex,
        semantic: SemanticIndex,
        *,
        retrieval_logger: RetrievalLogger | None = None,
    ) -> None:
        self.lexical = lexical
        self.semantic = semantic
        self.logger = retrieval_logger or RetrievalLogger()

    def search(
        self, query: str, *, top_k: int = 5, prefer_tests: bool = False
    ) -> list[EvidenceCandidate]:
        if top_k <= 0 or top_k > 100:
            raise ValueError("top_k must be between 1 and 100")
        started = time.perf_counter()
        pool_size = min(max(top_k * 4, 20), 200)
        lexical = self.lexical.search(query, limit=pool_size)
        semantic = self.semantic.search(query, limit=pool_size)
        candidates = self._merge(query, lexical, semantic, prefer_tests=prefer_tests)
        selected = candidates[:top_k]
        duration_ms = (time.perf_counter() - started) * 1_000
        safe_query = redact_text(query)[:2_000]
        self.logger.record(
            RetrievalLogEntry(
                query=safe_query,
                top_k=top_k,
                duration_ms=duration_ms,
                candidates=[
                    RetrievalCandidateLog(
                        chunk_id=candidate.chunk.id,
                        final_rank=rank,
                        lexical_rank=candidate.lexical_rank,
                        semantic_rank=candidate.semantic_rank,
                        lexical_score=candidate.lexical_score,
                        semantic_score=candidate.semantic_score,
                        final_score=candidate.final_score,
                    )
                    for rank, candidate in enumerate(selected, start=1)
                ],
            )
        )
        return selected

    @staticmethod
    def _merge(
        query: str,
        lexical: Sequence[SearchResult],
        semantic: Sequence[SearchResult],
        *,
        prefer_tests: bool,
    ) -> list[EvidenceCandidate]:
        by_id: dict[str, dict[str, SearchResult]] = {}
        for result in lexical:
            by_id.setdefault(result.chunk.id, {})["lexical"] = result
        for result in semantic:
            by_id.setdefault(result.chunk.id, {})["semantic"] = result

        query_terms = {term.lower() for term in _TERM.findall(query)}
        results: list[EvidenceCandidate] = []
        for chunk_id, sources in by_id.items():
            lexical_result = sources.get("lexical")
            semantic_result = sources.get("semantic")
            chunk = lexical_result or semantic_result
            if chunk is None:
                continue
            lexical_rank = lexical_result.rank if lexical_result else None
            semantic_rank = semantic_result.rank if semantic_result else None
            reciprocal_rank = (1 / (60 + lexical_rank) if lexical_rank else 0.0) + (
                1 / (60 + semantic_rank) if semantic_rank else 0.0
            )
            haystack = (
                f"{chunk.chunk.source_path} {chunk.chunk.symbol or ''} {chunk.chunk.text}"
            ).lower()
            matched = sorted(term for term in query_terms if term in haystack)
            rerank = min(len(matched), 8) * 0.015
            reasons: list[str] = []
            if matched:
                reasons.append("query_terms")
            identifier_terms = {term for term in query_terms if "_" in term or "." in term}
            if identifier_terms and any(term in haystack for term in identifier_terms):
                rerank += 0.08
                reasons.append("exact_identifier")
            if chunk.chunk.symbol and any(
                term in chunk.chunk.symbol.lower() for term in query_terms
            ):
                rerank += 0.06
                reasons.append("symbol_match")
            query_wants_tests = prefer_tests or "test" in query_terms or "regression" in query_terms
            if query_wants_tests and chunk.chunk.document_type.value == "test":
                rerank += 0.05
                reasons.append("test_role")
            path_terms = set(_TERM.findall(chunk.chunk.source_path.lower()))
            if query_terms & path_terms:
                rerank += 0.03
                reasons.append("path_match")
            results.append(
                EvidenceCandidate(
                    chunk=chunk.chunk,
                    lexical_rank=lexical_rank,
                    semantic_rank=semantic_rank,
                    lexical_score=lexical_result.score if lexical_result else None,
                    semantic_score=semantic_result.score if semantic_result else None,
                    rerank_score=rerank,
                    final_score=reciprocal_rank + rerank,
                    matched_terms=matched,
                    reasons=reasons,
                )
            )
        results.sort(key=lambda item: (-item.final_score, item.chunk.id))
        return results
