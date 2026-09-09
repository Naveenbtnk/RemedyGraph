"""Heading-aware document and Python AST symbol-aware chunking."""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass

from backend.app.ids import stable_id
from backend.app.rag.contracts import DocumentChunk, NormalizedDocument

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")


@dataclass(frozen=True)
class _Span:
    line_start: int
    line_end: int
    symbol: str | None = None


class DocumentChunker:
    def __init__(self, *, max_chars: int = 4_000, index_version: str = "day2-v1") -> None:
        if max_chars < 128:
            raise ValueError("max_chars must be at least 128")
        self.max_chars = max_chars
        self.index_version = index_version

    def chunk(self, document: NormalizedDocument) -> list[DocumentChunk]:
        if not document.markdown:
            return []
        if document.language == "python":
            spans = self._python_spans(document.markdown)
        else:
            spans = self._document_spans(document.markdown)
        lines = document.markdown.splitlines()
        chunks: list[DocumentChunk] = []
        for span in spans:
            text = "\n".join(lines[span.line_start - 1 : span.line_end])
            if not text.strip():
                continue
            chunks.extend(self._bounded_chunks(document, text, span))
        return chunks

    def _bounded_chunks(
        self, document: NormalizedDocument, text: str, span: _Span
    ) -> list[DocumentChunk]:
        source_lines = text.splitlines()
        result: list[DocumentChunk] = []
        offset = 0
        while offset < len(source_lines):
            end = offset
            chars = 0
            while end < len(source_lines):
                added = len(source_lines[end]) + (1 if end > offset else 0)
                if chars and chars + added > self.max_chars:
                    break
                chars += added
                end += 1
                if chars >= self.max_chars:
                    break
            if end == offset:
                end += 1
            chunk_text = "\n".join(source_lines[offset:end])
            line_start = span.line_start + offset
            line_end = span.line_start + end - 1
            content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            chunk_id = stable_id(
                "chunk", document.id, line_start, line_end, span.symbol or "", content_hash
            )
            result.append(
                DocumentChunk(
                    id=chunk_id,
                    document_id=document.id,
                    source_path=document.source_path,
                    text=chunk_text,
                    line_start=line_start,
                    line_end=line_end,
                    document_type=document.document_type,
                    language=document.language,
                    symbol=span.symbol,
                    content_hash=content_hash,
                    index_version=self.index_version,
                )
            )
            offset = end
        return result

    def _document_spans(self, text: str) -> list[_Span]:
        lines = text.splitlines()
        if not lines:
            return []
        starts = [index for index, line in enumerate(lines, start=1) if _HEADING.match(line)]
        if not starts:
            return self._paragraph_spans(lines)
        if starts[0] != 1:
            starts.insert(0, 1)
        return [
            _Span(start, (starts[index + 1] - 1) if index + 1 < len(starts) else len(lines))
            for index, start in enumerate(starts)
        ]

    @staticmethod
    def _paragraph_spans(lines: list[str]) -> list[_Span]:
        spans: list[_Span] = []
        start: int | None = None
        for index, line in enumerate(lines, start=1):
            if line.strip() and start is None:
                start = index
            if not line.strip() and start is not None:
                spans.append(_Span(start, index - 1))
                start = None
        if start is not None:
            spans.append(_Span(start, len(lines)))
        return spans

    @staticmethod
    def _python_spans(text: str) -> list[_Span]:
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return [_Span(1, len(lines))] if lines else []

        spans: list[_Span] = []
        symbol_lines: set[int] = set()

        def visit(body: list[ast.stmt], prefix: str = "") -> None:
            for node in body:
                if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                name = f"{prefix}.{node.name}" if prefix else node.name
                end_line = node.end_lineno or node.lineno
                decorator_lines = [decorator.lineno for decorator in node.decorator_list]
                start_line = min([node.lineno, *decorator_lines])
                spans.append(_Span(start_line, end_line, name))
                symbol_lines.update(range(start_line, end_line + 1))
                if isinstance(node, ast.ClassDef):
                    visit(node.body, name)

        visit(tree.body)
        module_ranges: list[_Span] = []
        range_start: int | None = None
        for line_number in range(1, len(lines) + 1):
            if line_number not in symbol_lines and lines[line_number - 1].strip():
                if range_start is None:
                    range_start = line_number
            elif range_start is not None:
                module_ranges.append(_Span(range_start, line_number - 1, "<module>"))
                range_start = None
        if range_start is not None:
            module_ranges.append(_Span(range_start, len(lines), "<module>"))
        return sorted([*spans, *module_ranges], key=lambda span: (span.line_start, span.line_end))
