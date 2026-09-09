"""Native text ingestion plus a constrained optional Microsoft MarkItDown adapter."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import mimetypes
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from backend.app.ids import stable_id
from backend.app.rag.contracts import (
    ConversionFailure,
    DocumentType,
    IngestionReport,
    NormalizedDocument,
)
from backend.app.rag.redaction import redact_text
from backend.app.rag.safety import IndexLimits, RepositoryFile, RepositoryWalker, WorkspaceBoundary

MARKITDOWN_SUFFIXES = frozenset({".pdf", ".docx", ".pptx"})
NATIVE_TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".css",
        ".go",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".md",
        ".markdown",
        ".py",
        ".rs",
        ".sh",
        ".sql",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)

_MIME_OVERRIDES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".py": "text/x-python",
    ".toml": "application/toml",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class ConversionError(RuntimeError):
    """A safe, user-displayable local conversion failure."""


class _LocalConverter(Protocol):
    def convert_local(self, path: str) -> object: ...


def _mime_type(path: Path) -> str:
    return _MIME_OVERRIDES.get(
        path.suffix.lower(), mimetypes.guess_type(path.name)[0] or "text/plain"
    )


def _document_type(source_path: str, suffix: str) -> DocumentType:
    path_lower = source_path.lower()
    name_lower = Path(source_path).name.lower()
    if suffix == ".py" and (
        name_lower.startswith("test_")
        or name_lower.endswith("_test.py")
        or "/tests/" in f"/{path_lower}/"
    ):
        return DocumentType.TEST
    if suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}:
        return DocumentType.CONFIGURATION
    if suffix in {
        ".css",
        ".go",
        ".html",
        ".java",
        ".js",
        ".py",
        ".rs",
        ".sh",
        ".sql",
        ".ts",
        ".tsx",
    }:
        return DocumentType.SOURCE
    return DocumentType.DOCUMENT


def _language(suffix: str) -> str | None:
    return {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
    }.get(suffix)


class NativeTextAdapter:
    """Decode supported repository text without network or external services."""

    name = "native-text"
    version = "1"

    def normalize(self, file: RepositoryFile) -> NormalizedDocument:
        suffix = file.absolute_path.suffix.lower()
        if suffix not in NATIVE_TEXT_SUFFIXES:
            raise ConversionError(f"unsupported native text type: {suffix or '<none>'}")
        raw = file.absolute_path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ConversionError("file is not valid UTF-8 text") from exc
        normalized = redact_text(text.replace("\r\n", "\n").replace("\r", "\n"))
        digest = hashlib.sha256(raw).hexdigest()
        return NormalizedDocument(
            id=stable_id("document", file.source_path, digest),
            source_path=file.source_path,
            source_filename=file.absolute_path.name,
            mime_type=_mime_type(file.absolute_path),
            sha256=digest,
            converter_name=self.name,
            converter_version=self.version,
            markdown=normalized,
            document_type=_document_type(file.source_path, suffix),
            language=_language(suffix),
        )


class MarkItDownAdapter:
    """Convert only validated local PDF/DOCX/PPTX files with optional features disabled."""

    name = "microsoft-markitdown"

    def __init__(
        self,
        workspace_root: Path,
        repository_root: Path,
        *,
        converter_factory: Callable[[], _LocalConverter] | None = None,
        converter_version: str | None = None,
    ) -> None:
        self.boundary = WorkspaceBoundary(workspace_root)
        self.repository_root = self.boundary.repository_root(repository_root)
        self._converter_factory = converter_factory or self._default_converter
        self.version = converter_version or self._installed_version()

    @staticmethod
    def _installed_version() -> str:
        try:
            return importlib.metadata.version("markitdown")
        except importlib.metadata.PackageNotFoundError:
            return "unavailable"

    @staticmethod
    def _default_converter() -> _LocalConverter:
        try:
            module = importlib.import_module("markitdown")
        except ImportError as exc:
            raise ConversionError(
                "MarkItDown support is not installed; install the 'documents' optional dependency"
            ) from exc
        converter_class = getattr(module, "MarkItDown", None)
        if converter_class is None:
            raise ConversionError("installed MarkItDown package has no MarkItDown converter")
        # Plugins, cloud endpoints, remote fetches, and LLM clients are intentionally absent.
        return cast(
            _LocalConverter,
            converter_class(
                enable_plugins=False,
                docintel_endpoint=None,
                cu_endpoint=None,
                llm_client=None,
                llm_model=None,
            ),
        )

    def normalize(self, file: RepositoryFile) -> NormalizedDocument:
        suffix = file.absolute_path.suffix.lower()
        if suffix not in MARKITDOWN_SUFFIXES:
            raise ConversionError("MarkItDown adapter permits only PDF, DOCX, and PPTX")
        if "://" in str(file.absolute_path):
            raise ConversionError("remote URLs are not accepted")
        safe_path = self.boundary.file(file.absolute_path, self.repository_root)
        source_path = safe_path.relative_to(self.repository_root).as_posix()
        try:
            result = self._converter_factory().convert_local(str(safe_path))
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError(f"MarkItDown conversion failed: {type(exc).__name__}") from exc
        markdown = getattr(result, "markdown", None) or getattr(result, "text_content", None)
        if not isinstance(markdown, str) or not markdown.strip():
            raise ConversionError("MarkItDown conversion produced no text")
        raw = safe_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        normalized = redact_text(markdown.replace("\r\n", "\n").replace("\r", "\n"))
        return NormalizedDocument(
            id=stable_id("document", source_path, digest),
            source_path=source_path,
            source_filename=safe_path.name,
            mime_type=_mime_type(safe_path),
            sha256=digest,
            converter_name=self.name,
            converter_version=self.version,
            markdown=normalized,
            document_type=DocumentType.DOCUMENT,
        )


class RepositoryIngestor:
    """Walk and normalize a repository while retaining bounded conversion failures."""

    def __init__(
        self,
        workspace_root: Path,
        repository_root: Path,
        *,
        limits: IndexLimits | None = None,
        markitdown_factory: Callable[[], _LocalConverter] | None = None,
        markitdown_version: str | None = None,
    ) -> None:
        self.walker = RepositoryWalker(workspace_root, limits)
        self.repository_root = self.walker.boundary.repository_root(repository_root)
        self.native = NativeTextAdapter()
        self.markitdown = MarkItDownAdapter(
            workspace_root,
            self.repository_root,
            converter_factory=markitdown_factory,
            converter_version=markitdown_version,
        )

    def ingest(self) -> IngestionReport:
        walk_report = self.walker.walk(self.repository_root)
        report = IngestionReport(
            skipped=walk_report.skipped.copy(), total_bytes=walk_report.total_bytes
        )
        for file in walk_report.files:
            try:
                if file.absolute_path.suffix.lower() in MARKITDOWN_SUFFIXES:
                    document = self.markitdown.normalize(file)
                else:
                    document = self.native.normalize(file)
            except (ConversionError, OSError) as exc:
                report.failures.append(
                    ConversionFailure(source_path=file.source_path, reason=str(exc))
                )
                continue
            report.documents.append(document)
        return report
