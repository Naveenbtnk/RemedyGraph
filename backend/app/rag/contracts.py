"""Typed contracts shared by repository ingestion, retrieval, and tools."""

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Self

from pydantic import Field, JsonValue, field_validator, model_validator

from backend.app.models import DomainModel


class DocumentType(StrEnum):
    DOCUMENT = "document"
    SOURCE = "source"
    CONFIGURATION = "configuration"
    TEST = "test"


class RetrievalSource(StrEnum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"


class ToolStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    DENIED = "denied"


class NormalizedDocument(DomainModel):
    """A local file normalized to bounded, redacted Markdown-compatible text."""

    id: str
    source_path: str
    source_filename: str
    mime_type: str
    sha256: str
    converter_name: str
    converter_version: str
    markdown: str
    document_type: DocumentType
    language: str | None = None

    @field_validator("source_path")
    @classmethod
    def source_path_is_relative(cls, value: str) -> str:
        return _relative_source_path(value)


class ConversionFailure(DomainModel):
    source_path: str
    reason: str


class IngestionReport(DomainModel):
    documents: list[NormalizedDocument] = Field(default_factory=list)
    failures: list[ConversionFailure] = Field(default_factory=list)
    skipped: dict[str, int] = Field(default_factory=dict)
    total_bytes: int = Field(default=0, ge=0)


class RepositoryIndexResult(DomainModel):
    documents_indexed: int = Field(ge=0)
    chunks_indexed: int = Field(ge=0)
    chunk_ids: list[str] = Field(default_factory=list)
    failures: list[ConversionFailure] = Field(default_factory=list)
    skipped: dict[str, int] = Field(default_factory=dict)
    total_bytes: int = Field(default=0, ge=0)


class DocumentChunk(DomainModel):
    id: str
    document_id: str
    source_path: str
    text: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    document_type: DocumentType
    language: str | None = None
    symbol: str | None = None
    content_hash: str
    index_version: str

    @field_validator("source_path")
    @classmethod
    def source_path_is_relative(cls, value: str) -> str:
        return _relative_source_path(value)

    @model_validator(mode="after")
    def line_range_is_ordered(self) -> Self:
        if self.line_end < self.line_start:
            raise ValueError("line_end must not precede line_start")
        return self


class SearchResult(DomainModel):
    chunk: DocumentChunk
    source: RetrievalSource
    rank: int = Field(ge=1)
    score: float


class EvidenceCandidate(DomainModel):
    chunk: DocumentChunk
    lexical_rank: int | None = Field(default=None, ge=1)
    semantic_rank: int | None = Field(default=None, ge=1)
    lexical_score: float | None = None
    semantic_score: float | None = None
    rerank_score: float = 0.0
    final_score: float
    matched_terms: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class RetrievalCandidateLog(DomainModel):
    chunk_id: str
    final_rank: int = Field(ge=1)
    lexical_rank: int | None = Field(default=None, ge=1)
    semantic_rank: int | None = Field(default=None, ge=1)
    lexical_score: float | None = None
    semantic_score: float | None = None
    final_score: float


class RetrievalLogEntry(DomainModel):
    query: str
    top_k: int = Field(ge=1)
    duration_ms: float = Field(ge=0)
    candidates: list[RetrievalCandidateLog] = Field(default_factory=list)


class ToolResultBase(DomainModel):
    tool: str
    status: ToolStatus
    duration_ms: float = Field(ge=0)
    truncated: bool = False
    error: str | None = None


class CodeSearchMatch(DomainModel):
    source_path: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    excerpt: str


class SearchCodeResult(ToolResultBase):
    matches: list[CodeSearchMatch] = Field(default_factory=list)


class SymbolDefinition(DomainModel):
    source_path: str
    symbol: str
    kind: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    signature: str
    excerpt: str


class GetSymbolResult(ToolResultBase):
    symbols: list[SymbolDefinition] = Field(default_factory=list)


class ConfigValue(DomainModel):
    source_path: str
    key_path: list[str | int]
    value: JsonValue


class InspectConfigResult(ToolResultBase):
    values: list[ConfigValue] = Field(default_factory=list)


class TestMatch(DomainModel):
    source_path: str
    symbol: str | None = None
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    excerpt: str


class FindTestsResult(ToolResultBase):
    matches: list[TestMatch] = Field(default_factory=list)


class GitChange(DomainModel):
    commit: str
    committed_at: str
    subject: str
    diff_excerpt: str


class FindGitChangesResult(ToolResultBase):
    changes: list[GitChange] = Field(default_factory=list)


def _relative_source_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if (
        not normalized
        or candidate.is_absolute()
        or ".." in candidate.parts
        or ":" in candidate.parts[0]
    ):
        raise ValueError("source_path must be a relative repository path")
    return candidate.as_posix()
