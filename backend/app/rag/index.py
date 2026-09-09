"""SQLite FTS5/BM25 lexical index for normalized repository chunks."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from backend.app.rag.contracts import (
    DocumentChunk,
    DocumentType,
    RetrievalSource,
    SearchResult,
)

_QUERY_TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:/-]{0,127}")


class LexicalIndex:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(database))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                text TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                language TEXT,
                symbol TEXT,
                content_hash TEXT NOT NULL,
                index_version TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id UNINDEXED,
                text,
                source_path,
                symbol,
                tokenize = 'unicode61 tokenchars ''_'''
            );
            """
        )

    def close(self) -> None:
        self.connection.close()

    def index(self, chunks: Sequence[DocumentChunk]) -> None:
        with self.connection:
            for chunk in chunks:
                self.connection.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk.id,))
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO chunks (
                        id, document_id, source_path, text, line_start, line_end,
                        document_type, language, symbol, content_hash, index_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.id,
                        chunk.document_id,
                        chunk.source_path,
                        chunk.text,
                        chunk.line_start,
                        chunk.line_end,
                        chunk.document_type.value,
                        chunk.language,
                        chunk.symbol,
                        chunk.content_hash,
                        chunk.index_version,
                    ),
                )
                self.connection.execute(
                    """INSERT INTO chunks_fts(chunk_id, text, source_path, symbol)
                    VALUES (?, ?, ?, ?)""",
                    (chunk.id, chunk.text, chunk.source_path, chunk.symbol or ""),
                )

    def search(self, query: str, *, limit: int = 20) -> list[SearchResult]:
        if limit <= 0:
            return []
        fts_query = self._fts_query(query)
        if not fts_query:
            return []
        rows = self.connection.execute(
            """
            SELECT c.*, bm25(chunks_fts, 0.0, 1.0, 2.0, 3.0) AS bm25_score
            FROM chunks_fts
            JOIN chunks AS c ON c.id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ?
            ORDER BY bm25_score ASC, c.id ASC
            LIMIT ?
            """,
            (fts_query, min(limit, 1_000)),
        ).fetchall()
        return [
            SearchResult(
                chunk=self._row_to_chunk(row),
                source=RetrievalSource.LEXICAL,
                rank=rank,
                score=-float(row["bm25_score"]),
            )
            for rank, row in enumerate(rows, start=1)
        ]

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = _QUERY_TOKEN.findall(query)[:32]
        return " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> DocumentChunk:
        return DocumentChunk(
            id=str(row["id"]),
            document_id=str(row["document_id"]),
            source_path=str(row["source_path"]),
            text=str(row["text"]),
            line_start=int(row["line_start"]),
            line_end=int(row["line_end"]),
            document_type=DocumentType(str(row["document_type"])),
            language=str(row["language"]) if row["language"] is not None else None,
            symbol=str(row["symbol"]) if row["symbol"] is not None else None,
            content_hash=str(row["content_hash"]),
            index_version=str(row["index_version"]),
        )
