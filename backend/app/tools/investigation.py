"""Bounded, typed, read-only repository investigation tools."""

from __future__ import annotations

import ast
import importlib
import json
import os
import re
import subprocess
import time
import tomllib
from collections.abc import Sequence
from pathlib import Path

from pydantic import JsonValue

from backend.app.rag.chunking import DocumentChunker
from backend.app.rag.contracts import (
    CodeSearchMatch,
    ConfigValue,
    FindGitChangesResult,
    FindTestsResult,
    GetSymbolResult,
    GitChange,
    InspectConfigResult,
    SearchCodeResult,
    SymbolDefinition,
    TestMatch,
    ToolStatus,
)
from backend.app.rag.ingestion import NativeTextAdapter
from backend.app.rag.redaction import redact_json, redact_text
from backend.app.rag.safety import IndexLimits, PathSafetyError, RepositoryFile, RepositoryWalker


class InvestigationTools:
    """Tools with fixed behavior; no call accepts or executes a command string."""

    def __init__(
        self,
        workspace_root: Path,
        repository_root: Path,
        *,
        limits: IndexLimits | None = None,
    ) -> None:
        self.walker = RepositoryWalker(workspace_root, limits)
        self.repository_root = self.walker.boundary.repository_root(repository_root)
        self.native = NativeTextAdapter()

    def _allowed_files(self) -> dict[str, RepositoryFile]:
        return {file.source_path: file for file in self.walker.walk(self.repository_root).files}

    def _allowed_file(self, source_path: str) -> RepositoryFile:
        if "://" in source_path:
            raise PathSafetyError("remote URLs are not accepted")
        requested = self.repository_root / Path(source_path)
        resolved = self.walker.boundary.file(requested, self.repository_root)
        normalized = resolved.relative_to(self.repository_root).as_posix()
        allowed = self._allowed_files().get(normalized)
        if allowed is None:
            raise PathSafetyError("file is ignored, unsupported, or outside configured limits")
        return allowed

    def search_code(
        self,
        pattern: str,
        *,
        regex: bool = False,
        source_path: str | None = None,
        max_results: int = 50,
        context_lines: int = 1,
        max_output_chars: int = 20_000,
    ) -> SearchCodeResult:
        started = time.perf_counter()
        if not pattern or len(pattern) > 512:
            return self._search_error(started, "pattern must contain 1 to 512 characters")
        if (
            not 1 <= max_results <= 200
            or not 0 <= context_lines <= 5
            or not 100 <= max_output_chars <= 100_000
        ):
            return self._search_error(started, "search bounds are invalid")
        if regex and self._unsafe_regex(pattern):
            return self._search_error(started, "regular expression uses a disallowed construct")
        try:
            matcher = re.compile(pattern) if regex else None
        except re.error as exc:
            return self._search_error(started, f"invalid regular expression: {exc}")
        try:
            files = (
                [self._allowed_file(source_path)]
                if source_path
                else list(self._allowed_files().values())
            )
        except PathSafetyError as exc:
            return SearchCodeResult(
                tool="search_code",
                status=ToolStatus.DENIED,
                duration_ms=self._elapsed(started),
                error=str(exc),
            )

        matches: list[CodeSearchMatch] = []
        output_chars = 0
        truncated = False
        for file in files:
            if file.absolute_path.suffix.lower() in {".pdf", ".docx", ".pptx"}:
                continue
            try:
                lines = file.absolute_path.read_text(encoding="utf-8-sig").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for index, line in enumerate(lines):
                found = matcher.search(line) is not None if matcher else pattern in line
                if not found:
                    continue
                start_index = max(0, index - context_lines)
                end_index = min(len(lines), index + context_lines + 1)
                excerpt = redact_text("\n".join(lines[start_index:end_index]))
                if output_chars + len(excerpt) > max_output_chars or len(matches) >= max_results:
                    truncated = True
                    break
                matches.append(
                    CodeSearchMatch(
                        source_path=file.source_path,
                        line_start=start_index + 1,
                        line_end=end_index,
                        excerpt=excerpt,
                    )
                )
                output_chars += len(excerpt)
            if truncated:
                break
        return SearchCodeResult(
            tool="search_code",
            status=ToolStatus.OK,
            duration_ms=self._elapsed(started),
            truncated=truncated,
            matches=matches,
        )

    def get_symbol(
        self, source_path: str, symbol: str, *, max_results: int = 20, max_excerpt: int = 8_000
    ) -> GetSymbolResult:
        started = time.perf_counter()
        if (
            not symbol
            or len(symbol) > 256
            or not 1 <= max_results <= 100
            or not 100 <= max_excerpt <= 20_000
        ):
            return GetSymbolResult(
                tool="get_symbol",
                status=ToolStatus.ERROR,
                duration_ms=self._elapsed(started),
                error="symbol or result bounds are invalid",
            )
        try:
            file = self._allowed_file(source_path)
        except PathSafetyError as exc:
            return GetSymbolResult(
                tool="get_symbol",
                status=ToolStatus.DENIED,
                duration_ms=self._elapsed(started),
                error=str(exc),
            )
        if file.absolute_path.suffix.lower() != ".py":
            return GetSymbolResult(
                tool="get_symbol",
                status=ToolStatus.ERROR,
                duration_ms=self._elapsed(started),
                error="get_symbol supports Python files only",
            )
        try:
            source = file.absolute_path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            return GetSymbolResult(
                tool="get_symbol",
                status=ToolStatus.ERROR,
                duration_ms=self._elapsed(started),
                error=f"Python parsing failed: {type(exc).__name__}",
            )
        source_lines = source.splitlines()
        definitions: list[SymbolDefinition] = []

        def visit(body: list[ast.stmt], prefix: str = "") -> None:
            for node in body:
                if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                qualified_name = f"{prefix}.{node.name}" if prefix else node.name
                if qualified_name == symbol or node.name == symbol:
                    end_line = node.end_lineno or node.lineno
                    excerpt = "\n".join(source_lines[node.lineno - 1 : end_line])
                    definitions.append(
                        SymbolDefinition(
                            source_path=file.source_path,
                            symbol=qualified_name,
                            kind=("class" if isinstance(node, ast.ClassDef) else "function"),
                            line_start=node.lineno,
                            line_end=end_line,
                            signature=redact_text(source_lines[node.lineno - 1].strip()),
                            excerpt=redact_text(excerpt[:max_excerpt]),
                        )
                    )
                if isinstance(node, ast.ClassDef):
                    visit(node.body, qualified_name)

        visit(tree.body)
        truncated = len(definitions) > max_results
        return GetSymbolResult(
            tool="get_symbol",
            status=ToolStatus.OK,
            duration_ms=self._elapsed(started),
            truncated=truncated,
            symbols=definitions[:max_results],
        )

    def inspect_config(
        self,
        source_path: str,
        key_path: Sequence[str | int] | str | None = None,
        *,
        max_output_chars: int = 20_000,
    ) -> InspectConfigResult:
        started = time.perf_counter()
        if not 100 <= max_output_chars <= 100_000:
            return InspectConfigResult(
                tool="inspect_config",
                status=ToolStatus.ERROR,
                duration_ms=self._elapsed(started),
                error="configuration output bound is invalid",
            )
        try:
            file = self._allowed_file(source_path)
        except PathSafetyError as exc:
            return InspectConfigResult(
                tool="inspect_config",
                status=ToolStatus.DENIED,
                duration_ms=self._elapsed(started),
                error=str(exc),
            )
        try:
            parsed = self._parse_config(file)
            resolved_path = self._normalize_key_path(key_path)
            selected = self._lookup(parsed, resolved_path)
            redacted = redact_json(selected, resolved_path[-1] if resolved_path else None)
        except Exception as exc:
            return InspectConfigResult(
                tool="inspect_config",
                status=ToolStatus.ERROR,
                duration_ms=self._elapsed(started),
                error=f"configuration inspection failed: {type(exc).__name__}",
            )
        serialized = json.dumps(redacted, sort_keys=True)
        truncated = len(serialized) > max_output_chars
        value: JsonValue = {"_truncated": serialized[:max_output_chars]} if truncated else redacted
        return InspectConfigResult(
            tool="inspect_config",
            status=ToolStatus.OK,
            duration_ms=self._elapsed(started),
            truncated=truncated,
            values=[ConfigValue(source_path=file.source_path, key_path=resolved_path, value=value)],
        )

    def find_tests(
        self, query: str, *, max_results: int = 50, max_output_chars: int = 20_000
    ) -> FindTestsResult:
        started = time.perf_counter()
        if (
            not query
            or len(query) > 512
            or not 1 <= max_results <= 200
            or not 100 <= max_output_chars <= 100_000
        ):
            return FindTestsResult(
                tool="find_tests",
                status=ToolStatus.ERROR,
                duration_ms=self._elapsed(started),
                error="query or result bounds are invalid",
            )
        terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_]+", query)}
        ranked: list[tuple[int, TestMatch]] = []
        for file in self._allowed_files().values():
            path = file.source_path.lower()
            name = file.absolute_path.name.lower()
            is_test = (
                name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{path}/"
            )
            if not is_test or file.absolute_path.suffix.lower() != ".py":
                continue
            try:
                document = self.native.normalize(file)
            except (OSError, RuntimeError):
                continue
            for chunk in DocumentChunker(max_chars=4_000).chunk(document):
                haystack = f"{chunk.symbol or ''} {chunk.text}".lower()
                score = sum(term in haystack for term in terms)
                if score:
                    ranked.append(
                        (
                            score,
                            TestMatch(
                                source_path=chunk.source_path,
                                symbol=chunk.symbol,
                                line_start=chunk.line_start,
                                line_end=chunk.line_end,
                                excerpt=chunk.text,
                            ),
                        )
                    )
        ranked.sort(key=lambda item: (-item[0], item[1].source_path, item[1].line_start))
        matches: list[TestMatch] = []
        output_chars = 0
        truncated = False
        for _, match in ranked:
            if len(matches) >= max_results or output_chars + len(match.excerpt) > max_output_chars:
                truncated = True
                break
            matches.append(match)
            output_chars += len(match.excerpt)
        return FindTestsResult(
            tool="find_tests",
            status=ToolStatus.OK,
            duration_ms=self._elapsed(started),
            truncated=truncated,
            matches=matches,
        )

    def find_git_changes(
        self,
        query: str = "",
        *,
        source_path: str | None = None,
        max_commits: int = 10,
        max_output_chars: int = 30_000,
        timeout_seconds: float = 5.0,
    ) -> FindGitChangesResult:
        started = time.perf_counter()
        if (
            len(query) > 256
            or not 1 <= max_commits <= 20
            or not 1_000 <= max_output_chars <= 100_000
            or not 0.1 <= timeout_seconds <= 10
        ):
            return FindGitChangesResult(
                tool="find_git_changes",
                status=ToolStatus.ERROR,
                duration_ms=self._elapsed(started),
                error="Git history bounds are invalid",
            )
        path_argument: list[str] = []
        if source_path is not None:
            try:
                file = self._allowed_file(source_path)
            except PathSafetyError as exc:
                return FindGitChangesResult(
                    tool="find_git_changes",
                    status=ToolStatus.DENIED,
                    duration_ms=self._elapsed(started),
                    error=str(exc),
                )
            path_argument = [file.source_path]
        command = [
            "git",
            "-C",
            str(self.repository_root),
            "--no-pager",
            "log",
            f"--max-count={max_commits}",
            "--format=%x1e%H%x1f%cI%x1f%s",
            "--no-ext-diff",
            "--unified=1",
            "-p",
        ]
        if query:
            command.append(f"--grep={query}")
        command.extend(["--", *path_argument])
        environment = {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        }
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return FindGitChangesResult(
                tool="find_git_changes",
                status=ToolStatus.ERROR,
                duration_ms=self._elapsed(started),
                error=f"Git history lookup failed: {type(exc).__name__}",
            )
        if completed.returncode != 0:
            return FindGitChangesResult(
                tool="find_git_changes",
                status=ToolStatus.ERROR,
                duration_ms=self._elapsed(started),
                error="Git history lookup failed",
            )
        changes: list[GitChange] = []
        output_chars = 0
        truncated = False
        for record in completed.stdout.split("\x1e"):
            record = record.strip()
            if not record:
                continue
            header, _, diff = record.partition("\n")
            header_parts = header.split("\x1f", maxsplit=2)
            if len(header_parts) != 3 or re.fullmatch(r"[0-9a-f]{40}", header_parts[0]) is None:
                continue
            safe_diff = redact_text(diff.strip())
            remaining = max_output_chars - output_chars
            if remaining <= 0:
                truncated = True
                break
            if len(safe_diff) > remaining:
                safe_diff = safe_diff[:remaining]
                truncated = True
            changes.append(
                GitChange(
                    commit=header_parts[0],
                    committed_at=header_parts[1],
                    subject=redact_text(header_parts[2]),
                    diff_excerpt=safe_diff,
                )
            )
            output_chars += len(safe_diff)
            if truncated:
                break
        return FindGitChangesResult(
            tool="find_git_changes",
            status=ToolStatus.OK,
            duration_ms=self._elapsed(started),
            truncated=truncated,
            changes=changes,
        )

    @staticmethod
    def _parse_config(file: RepositoryFile) -> object:
        text = file.absolute_path.read_text(encoding="utf-8-sig")
        suffix = file.absolute_path.suffix.lower()
        if suffix == ".json":
            return json.loads(text)
        if suffix == ".toml":
            return tomllib.loads(text)
        if suffix in {".yaml", ".yml"}:
            yaml = importlib.import_module("yaml")
            return yaml.safe_load(text)
        raise ValueError("inspect_config supports JSON, YAML, and TOML only")

    @staticmethod
    def _normalize_key_path(key_path: Sequence[str | int] | str | None) -> list[str | int]:
        if key_path is None:
            return []
        if isinstance(key_path, str):
            if len(key_path) > 1_000:
                raise ValueError("key path is too long")
            return [int(part) if part.isdigit() else part for part in key_path.split(".") if part]
        if len(key_path) > 64:
            raise ValueError("key path has too many segments")
        return list(key_path)

    @staticmethod
    def _lookup(value: object, key_path: Sequence[str | int]) -> object:
        current = value
        for part in key_path:
            if isinstance(part, int) and isinstance(current, list):
                current = current[part]
            elif isinstance(part, str) and isinstance(current, dict):
                current = current[part]
            else:
                raise KeyError(f"key path segment not found: {part}")
        return current

    @staticmethod
    def _search_error(started: float, error: str) -> SearchCodeResult:
        return SearchCodeResult(
            tool="search_code",
            status=ToolStatus.ERROR,
            duration_ms=InvestigationTools._elapsed(started),
            error=error,
        )

    @staticmethod
    def _unsafe_regex(pattern: str) -> bool:
        """Reject lookarounds, backreferences, and quantified groups prone to runaway work."""

        return (
            "(?" in pattern
            or re.search(r"\\[1-9]", pattern) is not None
            or re.search(r"\([^)]*[+*][^)]*\)[+*{]", pattern) is not None
        )

    @staticmethod
    def _elapsed(started: float) -> float:
        return max(0.0, (time.perf_counter() - started) * 1_000)
