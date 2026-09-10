"""Allowlisted deterministic checks for configuration, static code, and test protection."""

from __future__ import annotations

import ast
import json
import re
import time
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from backend.app.audit.contracts import (
    CheckExecution,
    CheckOperator,
    CheckOutcome,
    DeterministicCheckResult,
    DeterministicCheckSpec,
    DeterministicCheckType,
    EvidenceRecord,
    EvidenceRole,
    RequirementAvailability,
)
from backend.app.ids import stable_id
from backend.app.models import EvidenceKind
from backend.app.rag.redaction import redact_text
from backend.app.rag.safety import IndexLimits, RepositoryFile, RepositoryWalker


class DeterministicCheckRunner:
    """Execute a closed set of typed checks; model-provided commands are never accepted."""

    def __init__(
        self,
        workspace_root: Path,
        repository_root: Path,
        *,
        limits: IndexLimits | None = None,
    ) -> None:
        self.walker = RepositoryWalker(workspace_root, limits)
        self.repository_root = self.walker.boundary.repository_root(repository_root)

    def run(
        self,
        spec: DeterministicCheckSpec,
        *,
        run_id: str,
        action_id: str,
    ) -> CheckExecution:
        started = time.perf_counter()
        if spec.availability != RequirementAvailability.SUPPORTED:
            outcome = (
                CheckOutcome.UNAVAILABLE
                if spec.availability == RequirementAvailability.UNAVAILABLE
                else CheckOutcome.UNSUPPORTED
            )
            return self._non_assessable(spec, run_id, action_id, outcome, started)
        try:
            if spec.check_type == DeterministicCheckType.CONFIGURATION_VALUE:
                return self._configuration(spec, run_id, action_id, started)
            if spec.check_type == DeterministicCheckType.STATIC_CODE:
                return self._static_code(spec, run_id, action_id, started)
            if spec.check_type == DeterministicCheckType.STATIC_PATTERN:
                return self._static_pattern(spec, run_id, action_id, started)
            if spec.check_type == DeterministicCheckType.TEST_PROTECTION:
                return self._test_protection(spec, run_id, action_id, started)
        except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
            result = DeterministicCheckResult(
                id=stable_id("check_result", run_id, spec.id),
                run_id=run_id,
                invariant_id=spec.invariant_id,
                check_spec_id=spec.id,
                outcome=CheckOutcome.ERROR,
                core=spec.core,
                detail=f"deterministic check failed safely: {type(exc).__name__}",
                expected=spec.expected,
                duration_ms=self._elapsed(started),
            )
            return CheckExecution(result=result)
        return self._non_assessable(spec, run_id, action_id, CheckOutcome.UNSUPPORTED, started)

    def _configuration(
        self,
        spec: DeterministicCheckSpec,
        run_id: str,
        action_id: str,
        started: float,
    ) -> CheckExecution:
        candidates = [str(value) for value in spec.parameters.get("key_candidates", [])]
        expected = spec.expected
        if not candidates or not isinstance(expected, (int, float)) or isinstance(expected, bool):
            raise ValueError("configuration check requires numeric expected and key candidates")
        observations: list[dict[str, Any]] = []
        evidence: list[EvidenceRecord] = []
        for source_path, key, value, line in self._configuration_values():
            if not self._key_matches(key, candidates):
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            converted_expected = self._expected_for_key(float(expected), spec.unit, key)
            passed = self._compare(float(value), converted_expected, spec.operator)
            observations.append({"path": source_path, "key": key, "value": value, "passed": passed})
            evidence.append(
                EvidenceRecord(
                    id=stable_id("evidence", run_id, spec.id, source_path, key, value),
                    run_id=run_id,
                    action_id=action_id,
                    invariant_id=spec.invariant_id,
                    kind=(
                        EvidenceKind.CODE
                        if source_path.endswith(".py")
                        else EvidenceKind.CONFIGURATION
                    ),
                    role=EvidenceRole.SUPPORTING if passed else EvidenceRole.CONTRADICTORY,
                    source_path=source_path,
                    line_start=line,
                    line_end=line,
                    excerpt=redact_text(f"{key} = {value}"),
                    metadata={"key": key, "operator": spec.operator.value},
                )
            )
        if not observations:
            evidence = [self._absence(spec, run_id, action_id, "no matching effective value found")]
            outcome, passed, detail = (
                CheckOutcome.NOT_FOUND,
                False,
                "no matching effective value found",
            )
        else:
            passed = all(bool(item["passed"]) for item in observations)
            outcome = CheckOutcome.PASSED if passed else CheckOutcome.FAILED
            detail = (
                "all matching values satisfy the required threshold"
                if passed
                else "at least one matching value contradicts the required threshold"
            )
        return CheckExecution(
            result=DeterministicCheckResult(
                id=stable_id("check_result", run_id, spec.id),
                run_id=run_id,
                invariant_id=spec.invariant_id,
                check_spec_id=spec.id,
                outcome=outcome,
                passed=passed,
                core=spec.core,
                expected=spec.expected,
                actual=observations,
                detail=detail,
                evidence_ids=[item.id for item in evidence],
                duration_ms=self._elapsed(started),
            ),
            evidence=evidence,
        )

    def _static_pattern(
        self,
        spec: DeterministicCheckSpec,
        run_id: str,
        action_id: str,
        started: float,
    ) -> CheckExecution:
        pattern = spec.parameters.get("literal_pattern")
        if not isinstance(pattern, str) or not pattern or len(pattern) > 200:
            raise ValueError("static pattern must be a non-empty literal of at most 200 characters")
        evidence: list[EvidenceRecord] = []
        for file in self.walker.walk(self.repository_root).files:
            if len(evidence) >= 20:
                break
            if file.absolute_path.suffix.lower() not in {
                ".py",
                ".json",
                ".toml",
                ".yaml",
                ".yml",
                ".ini",
                ".cfg",
                ".md",
            }:
                continue
            for line_number, line in enumerate(
                file.absolute_path.read_text(encoding="utf-8-sig").splitlines(), start=1
            ):
                if pattern not in line:
                    continue
                evidence.append(
                    EvidenceRecord(
                        id=stable_id(
                            "evidence", run_id, spec.id, file.source_path, line_number, pattern
                        ),
                        run_id=run_id,
                        action_id=action_id,
                        invariant_id=spec.invariant_id,
                        kind=EvidenceKind.CODE,
                        role=EvidenceRole.SUPPORTING_ONLY,
                        source_path=file.source_path,
                        line_start=line_number,
                        line_end=line_number,
                        excerpt=redact_text(line.strip()),
                        metadata={"proof_kind": "bounded_literal_pattern"},
                    )
                )
                if len(evidence) >= 20:
                    break
        passed = bool(evidence)
        if not evidence:
            evidence = [self._absence(spec, run_id, action_id, "literal pattern not found")]
        return CheckExecution(
            result=DeterministicCheckResult(
                id=stable_id("check_result", run_id, spec.id),
                run_id=run_id,
                invariant_id=spec.invariant_id,
                check_spec_id=spec.id,
                outcome=CheckOutcome.PASSED if passed else CheckOutcome.NOT_FOUND,
                passed=passed,
                core=spec.core,
                expected=pattern,
                actual=len(evidence) if passed else 0,
                detail="bounded literal pattern located" if passed else "literal pattern not found",
                evidence_ids=[item.id for item in evidence],
                duration_ms=self._elapsed(started),
            ),
            evidence=evidence,
        )

    def _static_code(
        self,
        spec: DeterministicCheckSpec,
        run_id: str,
        action_id: str,
        started: float,
    ) -> CheckExecution:
        terms = [self._normalize_key(str(value)) for value in spec.parameters.get("terms", [])]
        terms = [term for term in terms if term]
        if not terms:
            raise ValueError("static check requires terms")
        found: dict[str, list[tuple[str, int, str, str]]] = {term: [] for term in terms}
        for file in self.walker.walk(self.repository_root).files:
            if self._is_test(file.source_path):
                continue
            suffix = file.absolute_path.suffix.lower()
            if suffix == ".py":
                self._scan_python(file, found)
            elif suffix in {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg"}:
                self._scan_configured_use(file, found)
        missing = [term for term, matches in found.items() if not matches]
        evidence: list[EvidenceRecord] = []
        for term, matches in found.items():
            for source_path, line, excerpt, proof_kind in matches[:5]:
                evidence.append(
                    EvidenceRecord(
                        id=stable_id("evidence", run_id, spec.id, term, source_path, line),
                        run_id=run_id,
                        action_id=action_id,
                        invariant_id=spec.invariant_id,
                        kind=(
                            EvidenceKind.CODE
                            if source_path.endswith(".py")
                            else EvidenceKind.CONFIGURATION
                        ),
                        role=EvidenceRole.SUPPORTING,
                        source_path=source_path,
                        line_start=line,
                        line_end=line,
                        excerpt=redact_text(excerpt),
                        metadata={"matched_term": term, "proof_kind": proof_kind},
                    )
                )
        if missing:
            evidence.append(
                self._absence(
                    spec, run_id, action_id, f"missing executable terms: {', '.join(missing)}"
                )
            )
        passed = not missing
        return CheckExecution(
            result=DeterministicCheckResult(
                id=stable_id("check_result", run_id, spec.id),
                run_id=run_id,
                invariant_id=spec.invariant_id,
                check_spec_id=spec.id,
                outcome=CheckOutcome.PASSED if passed else CheckOutcome.NOT_FOUND,
                passed=passed,
                core=spec.core,
                expected={"terms": terms},
                actual={term: len(matches) for term, matches in found.items()},
                detail=(
                    "all material terms occur in calls, wiring, or enabled configuration"
                    if passed
                    else "required executable terms were not found"
                ),
                evidence_ids=[item.id for item in evidence],
                duration_ms=self._elapsed(started),
            ),
            evidence=evidence,
        )

    def _test_protection(
        self,
        spec: DeterministicCheckSpec,
        run_id: str,
        action_id: str,
        started: float,
    ) -> CheckExecution:
        query = self._test_query(str(spec.parameters.get("query", "")))
        query_terms = [self._normalize_key(str(term)) for term in spec.parameters.get("terms", [])]
        query_terms = [term for term in query_terms if term] or [
            self._normalize_key(term) for term in query.split()
        ]
        matches: list[tuple[str, str, int, int, str]] = []
        for file in self.walker.walk(self.repository_root).files:
            if file.absolute_path.suffix.lower() != ".py" or not self._is_test(file.source_path):
                continue
            matches.extend(self._structural_test_matches(file, query_terms))
        evidence = [
            EvidenceRecord(
                id=stable_id("evidence", run_id, spec.id, source_path, line_start),
                run_id=run_id,
                action_id=action_id,
                invariant_id=spec.invariant_id,
                kind=EvidenceKind.TEST,
                role=EvidenceRole.SUPPORTING,
                source_path=source_path,
                line_start=line_start,
                line_end=line_end,
                excerpt=redact_text(excerpt),
                metadata={"symbol": symbol, "proof_kind": "nontrivial_structural_test"},
            )
            for source_path, symbol, line_start, line_end, excerpt in matches
        ]
        if not evidence:
            evidence = [
                self._absence(
                    spec, run_id, action_id, "no matching behavioral test assertion found"
                )
            ]
        passed = bool(matches)
        return CheckExecution(
            result=DeterministicCheckResult(
                id=stable_id("check_result", run_id, spec.id),
                run_id=run_id,
                invariant_id=spec.invariant_id,
                check_spec_id=spec.id,
                outcome=CheckOutcome.PASSED if passed else CheckOutcome.NOT_FOUND,
                passed=passed,
                core=spec.core,
                expected="a located executable behavioral assertion",
                actual=[{"path": path, "symbol": symbol} for path, symbol, *_ in matches],
                detail=(
                    "behavioral test assertion located"
                    if passed
                    else "no matching behavioral test assertion found"
                ),
                evidence_ids=[item.id for item in evidence],
                duration_ms=self._elapsed(started),
            ),
            evidence=evidence,
        )

    def _configuration_values(self) -> Iterator[tuple[str, str, object, int]]:
        for file in self.walker.walk(self.repository_root).files:
            suffix = file.absolute_path.suffix.lower()
            if suffix == ".py":
                try:
                    tree = ast.parse(file.absolute_path.read_text(encoding="utf-8-sig"))
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                        continue
                    value_node = node.value
                    if not isinstance(value_node, ast.Constant):
                        continue
                    constant_value = value_node.value
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            yield file.source_path, target.id, constant_value, node.lineno
                continue
            if suffix not in {".json", ".toml", ".yaml", ".yml"}:
                continue
            try:
                text = file.absolute_path.read_text(encoding="utf-8-sig")
                if suffix == ".json":
                    parsed = json.loads(text)
                elif suffix == ".toml":
                    parsed = tomllib.loads(text)
                else:
                    parsed = yaml.safe_load(text)
            except (ValueError, TypeError, yaml.YAMLError):
                continue
            for key, flattened_value in self._flatten(parsed):
                key_name = str(key[-1]) if key else ""
                line = self._find_key_line(text, key_name)
                yield (
                    file.source_path,
                    ".".join(str(part) for part in key),
                    flattened_value,
                    line,
                )

    @classmethod
    def _flatten(
        cls, value: object, path: tuple[str | int, ...] = ()
    ) -> Iterator[tuple[tuple[str | int, ...], object]]:
        if isinstance(value, dict):
            for key, nested in value.items():
                yield from cls._flatten(nested, (*path, str(key)))
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                yield from cls._flatten(nested, (*path, index))
        else:
            yield path, value

    @staticmethod
    def _find_key_line(text: str, key: str) -> int:
        pattern = re.compile(rf"(?:^|[\"']){re.escape(key)}(?:[\"']|\s*[:=])")
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line.strip()):
                return number
        return 1

    @classmethod
    def _key_matches(cls, key: str, candidates: list[str]) -> bool:
        normalized = cls._normalize_key(key)
        return any(normalized.endswith(cls._normalize_key(candidate)) for candidate in candidates)

    @staticmethod
    def _normalize_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    @staticmethod
    def _expected_for_key(expected: float, unit: str | None, key: str) -> float:
        lowered = key.lower()
        if unit == "seconds" and (lowered.endswith("_ms") or "milliseconds" in lowered):
            return expected * 1_000
        if unit == "minutes" and (lowered.endswith("_seconds") or lowered.endswith("_secs")):
            return expected * 60
        if unit == "percent" and "ratio" in lowered:
            return expected / 100
        return expected

    @staticmethod
    def _compare(actual: float, expected: float, operator: CheckOperator) -> bool:
        if operator == CheckOperator.EQUALS:
            return actual == expected
        if operator == CheckOperator.LESS_THAN_OR_EQUAL:
            return actual <= expected
        if operator == CheckOperator.GREATER_THAN_OR_EQUAL:
            return actual >= expected
        return True

    def _scan_python(
        self, file: RepositoryFile, found: dict[str, list[tuple[str, int, str, str]]]
    ) -> None:
        source = file.absolute_path.read_text(encoding="utf-8-sig")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        lines = source.splitlines()
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            proof_kind: str | None = None
            value = ""
            if isinstance(node, ast.Call):
                value = ast.unparse(node.func)
                proof_kind = "call"
            elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
                parent = parents.get(node)
                if isinstance(
                    parent,
                    (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Return, ast.If, ast.Compare),
                ):
                    value = ast.unparse(node)
                    proof_kind = "wiring"
                elif isinstance(parent, ast.Call) and node is not parent.func:
                    value = ast.unparse(node)
                    proof_kind = "wiring"
                elif isinstance(parent, ast.keyword):
                    value = ast.unparse(node)
                    proof_kind = "wiring"
            if proof_kind is None or not hasattr(node, "lineno"):
                continue
            haystack = self._normalize_key(value)
            for term in found:
                if term in haystack:
                    line = int(node.lineno)
                    match = (file.source_path, line, lines[line - 1].strip(), proof_kind)
                    if match not in found[term]:
                        found[term].append(match)

    def _scan_configured_use(
        self, file: RepositoryFile, found: dict[str, list[tuple[str, int, str, str]]]
    ) -> None:
        text = file.absolute_path.read_text(encoding="utf-8-sig")
        suffix = file.absolute_path.suffix.lower()
        try:
            if suffix == ".json":
                parsed = json.loads(text)
            elif suffix == ".toml":
                parsed = tomllib.loads(text)
            elif suffix in {".yaml", ".yml"}:
                parsed = yaml.safe_load(text)
            else:
                return
        except (ValueError, TypeError, yaml.YAMLError):
            return
        for key_path, value in self._flatten(parsed):
            if value in {None, False, 0, ""}:
                continue
            key = ".".join(str(part) for part in key_path)
            if isinstance(value, str) and self._normalize_key(value) in {
                self._normalize_key(key),
                *found.keys(),
            }:
                continue
            haystack = self._normalize_key(key)
            for term in found:
                if term in haystack:
                    line = self._find_key_line(text, str(key_path[-1]) if key_path else "")
                    excerpt = f"{key} = {value!r}"
                    found[term].append((file.source_path, line, excerpt, "enabled_configuration"))

    def _structural_test_matches(
        self, file: RepositoryFile, terms: list[str]
    ) -> list[tuple[str, str, int, int, str]]:
        source = file.absolute_path.read_text(encoding="utf-8-sig")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        lines = source.splitlines()
        imported = {
            alias.asname or alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        matches: list[tuple[str, str, int, int, str]] = []
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test")
        ):
            exercised_refs = self._exercised_references(function, imported)
            if not exercised_refs:
                continue
            haystack = self._normalize_key(" ".join(exercised_refs))
            if terms and not any(term in haystack for term in terms):
                continue
            end_line = int(getattr(function, "end_lineno", function.lineno))
            excerpt = "\n".join(lines[function.lineno - 1 : end_line])
            matches.append((file.source_path, function.name, function.lineno, end_line, excerpt))
        return matches

    @classmethod
    def _exercised_references(
        cls, function: ast.FunctionDef | ast.AsyncFunctionDef, imported: set[str]
    ) -> set[str]:
        assignments: dict[str, str] = {}
        for node in ast.walk(function):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(
                node.value, ast.Call
            ):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            called = ast.unparse(node.value.func)
            if cls._root_name(node.value.func) not in imported:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = called

        references: set[str] = set()
        assertions = [node.test for node in ast.walk(function) if isinstance(node, ast.Assert)]
        raise_bodies = [
            child
            for node in ast.walk(function)
            if isinstance(node, ast.With)
            and any("pytest.raises" in ast.unparse(item.context_expr) for item in node.items)
            for statement in node.body
            for child in ast.walk(statement)
        ]
        for expression in [*assertions, *raise_bodies]:
            for node in ast.walk(expression):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    if node.id in imported:
                        references.add(node.id)
                    if node.id in assignments:
                        references.add(assignments[node.id])
                elif isinstance(node, ast.Call) and cls._root_name(node.func) in imported:
                    references.add(ast.unparse(node.func))
        return references

    @staticmethod
    def _root_name(expression: ast.expr) -> str | None:
        while isinstance(expression, ast.Attribute):
            expression = expression.value
        return expression.id if isinstance(expression, ast.Name) else None

    @staticmethod
    def _is_test(source_path: str) -> bool:
        lowered = source_path.lower()
        name = Path(source_path).name.lower()
        return name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{lowered}/"

    @staticmethod
    def _test_query(value: str) -> str:
        stop = {
            "a",
            "add",
            "an",
            "for",
            "regression",
            "the",
            "to",
            "with",
        }
        stems = {"retries": "retry", "tests": "test"}
        terms = [
            stems.get(term.lower(), term.lower())
            for term in re.findall(r"[A-Za-z_][A-Za-z0-9_-]+", value)
            if term.lower() not in stop
        ]
        return " ".join(terms)

    @staticmethod
    def _absence(
        spec: DeterministicCheckSpec, run_id: str, action_id: str, detail: str
    ) -> EvidenceRecord:
        return EvidenceRecord(
            id=stable_id("evidence", run_id, spec.id, "absent", detail),
            run_id=run_id,
            action_id=action_id,
            invariant_id=spec.invariant_id,
            kind=EvidenceKind.ABSENT,
            role=EvidenceRole.MISSING,
            excerpt=detail,
        )

    def _non_assessable(
        self,
        spec: DeterministicCheckSpec,
        run_id: str,
        action_id: str,
        outcome: CheckOutcome,
        started: float,
    ) -> CheckExecution:
        reason = spec.unavailable_reason or "no supported deterministic check is available"
        role = (
            EvidenceRole.UNAVAILABLE
            if outcome == CheckOutcome.UNAVAILABLE
            else EvidenceRole.MISSING
        )
        evidence = EvidenceRecord(
            id=stable_id("evidence", run_id, spec.id, outcome.value),
            run_id=run_id,
            action_id=action_id,
            invariant_id=spec.invariant_id,
            kind=EvidenceKind.ABSENT,
            role=role,
            excerpt=reason,
        )
        result = DeterministicCheckResult(
            id=stable_id("check_result", run_id, spec.id),
            run_id=run_id,
            invariant_id=spec.invariant_id,
            check_spec_id=spec.id,
            outcome=outcome,
            core=spec.core,
            expected=spec.expected,
            detail=reason,
            evidence_ids=[evidence.id],
            duration_ms=self._elapsed(started),
        )
        return CheckExecution(result=result, evidence=[evidence])

    @staticmethod
    def _elapsed(started: float) -> float:
        return max(0.0, (time.perf_counter() - started) * 1_000)
