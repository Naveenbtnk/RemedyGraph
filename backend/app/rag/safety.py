"""Canonical workspace containment and bounded repository walking."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


class PathSafetyError(ValueError):
    """Raised when a requested path crosses the configured repository boundary."""


@dataclass(frozen=True)
class IndexLimits:
    max_file_bytes: int = 1_000_000
    max_index_bytes: int = 25_000_000
    max_files: int = 10_000

    def __post_init__(self) -> None:
        if min(self.max_file_bytes, self.max_index_bytes, self.max_files) <= 0:
            raise ValueError("index limits must be positive")


@dataclass(frozen=True)
class RepositoryFile:
    absolute_path: Path
    source_path: str
    size_bytes: int


@dataclass
class WalkReport:
    files: list[RepositoryFile] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    total_bytes: int = 0

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".next",
        ".pnpm-store",
        ".pytest_cache",
        ".remedygraph",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".yarn",
        "__pycache__",
        "bower_components",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
        "out",
        "site-packages",
        "target",
        "vendor",
        "venv",
    }
)

IGNORED_FILENAMES = frozenset(
    {
        ".env",
        ".npmrc",
        ".pypirc",
        "credentials",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "secrets.json",
    }
)

IGNORED_SUFFIXES = frozenset(
    {
        ".7z",
        ".a",
        ".avi",
        ".bin",
        ".bmp",
        ".class",
        ".db",
        ".dll",
        ".dylib",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".jpeg",
        ".jpg",
        ".key",
        ".lock",
        ".mov",
        ".mp3",
        ".mp4",
        ".o",
        ".obj",
        ".p12",
        ".pfx",
        ".png",
        ".pyc",
        ".sqlite",
        ".sqlite3",
        ".so",
        ".tar",
        ".wav",
        ".webm",
        ".webp",
        ".whl",
        ".zip",
    }
)

SUPPORTED_SUFFIXES = frozenset(
    {
        ".cfg",
        ".css",
        ".docx",
        ".go",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".md",
        ".markdown",
        ".pdf",
        ".pptx",
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


class WorkspaceBoundary:
    """Resolve paths and prove that they stay under a configured workspace/repository."""

    def __init__(self, workspace_root: Path) -> None:
        try:
            self.workspace_root = workspace_root.expanduser().resolve(strict=True)
        except OSError as exc:
            raise PathSafetyError("WORKSPACE_ROOT must be an existing directory") from exc
        if not self.workspace_root.is_dir():
            raise PathSafetyError("WORKSPACE_ROOT must be an existing directory")

    @staticmethod
    def _within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    def repository_root(self, requested: Path) -> Path:
        try:
            resolved = requested.expanduser().resolve(strict=True)
        except OSError as exc:
            raise PathSafetyError("repository must be an existing directory") from exc
        if not resolved.is_dir() or not self._within(resolved, self.workspace_root):
            raise PathSafetyError("repository must be an existing directory inside WORKSPACE_ROOT")
        return resolved

    def file(self, requested: Path, repository_root: Path) -> Path:
        root = self.repository_root(repository_root)
        try:
            resolved = requested.expanduser().resolve(strict=True)
        except OSError as exc:
            raise PathSafetyError("requested path must be an existing file") from exc
        if not resolved.is_file():
            raise PathSafetyError("requested path must be an existing file")
        if not self._within(resolved, root) or not self._within(resolved, self.workspace_root):
            raise PathSafetyError("requested path escapes the repository or WORKSPACE_ROOT")
        return resolved


class RepositoryWalker:
    """Walk supported repository files without following unsafe or irrelevant content."""

    def __init__(self, workspace_root: Path, limits: IndexLimits | None = None) -> None:
        self.boundary = WorkspaceBoundary(workspace_root)
        self.limits = limits or IndexLimits()

    def walk(self, repository: Path) -> WalkReport:
        root = self.boundary.repository_root(repository)
        report = WalkReport()

        for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            kept_directories: list[str] = []
            for name in sorted(directory_names):
                child = current_path / name
                if name.lower() in IGNORED_DIRECTORIES:
                    report.skip("ignored_directory")
                elif child.is_symlink():
                    report.skip("symlink")
                else:
                    try:
                        resolved_child = child.resolve(strict=True)
                    except OSError:
                        report.skip("unreadable")
                        continue
                    if WorkspaceBoundary._within(resolved_child, root):
                        kept_directories.append(name)
                    else:
                        report.skip("path_escape")
            directory_names[:] = kept_directories

            for name in sorted(file_names):
                candidate = current_path / name
                reason = self._denial_reason(candidate)
                if reason is not None:
                    report.skip(reason)
                    continue
                try:
                    resolved = self.boundary.file(candidate, root)
                    size = resolved.stat().st_size
                except (OSError, PathSafetyError):
                    report.skip("unreadable_or_escape")
                    continue
                if size > self.limits.max_file_bytes:
                    report.skip("oversized_file")
                    continue
                if report.total_bytes + size > self.limits.max_index_bytes:
                    report.skip("max_index_bytes")
                    continue
                try:
                    looks_binary = self._looks_binary(resolved)
                except OSError:
                    report.skip("unreadable")
                    continue
                if looks_binary:
                    report.skip("binary")
                    continue
                if len(report.files) >= self.limits.max_files:
                    report.skip("max_files")
                    continue
                report.files.append(
                    RepositoryFile(
                        absolute_path=resolved,
                        source_path=resolved.relative_to(root).as_posix(),
                        size_bytes=size,
                    )
                )
                report.total_bytes += size
        return report

    @staticmethod
    def _denial_reason(path: Path) -> str | None:
        lower_name = path.name.lower()
        suffix = path.suffix.lower()
        if path.is_symlink():
            return "symlink"
        secret_parts = set(lower_name.replace("-", ".").replace("_", ".").split("."))
        if (
            lower_name in IGNORED_FILENAMES
            or lower_name.startswith(".env.")
            or bool(secret_parts & {"credential", "credentials", "secret", "secrets"})
        ):
            return "secret_file"
        if suffix in IGNORED_SUFFIXES:
            return "ignored_extension"
        if suffix not in SUPPORTED_SUFFIXES:
            return "unsupported_extension"
        return None

    @staticmethod
    def _looks_binary(path: Path) -> bool:
        if path.suffix.lower() in {".pdf", ".docx", ".pptx"}:
            return False
        with path.open("rb") as stream:
            sample = stream.read(8192)
        if b"\x00" in sample:
            return True
        if not sample:
            return False
        control = sum(byte < 9 or 13 < byte < 32 for byte in sample)
        return control / len(sample) > 0.05
