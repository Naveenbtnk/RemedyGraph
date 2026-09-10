"""Deterministic conversion of atomic corrective actions into measurable requirements."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.audit.contracts import (
    CheckOperator,
    CompiledInvariant,
    DeterministicCheckSpec,
    DeterministicCheckType,
    RequirementAvailability,
    RequirementKind,
    SourceLocation,
)
from backend.app.ids import stable_id
from backend.app.models import ActionItem


@dataclass(frozen=True)
class CompilationResult:
    invariants: list[CompiledInvariant]
    check_specs: list[DeterministicCheckSpec]


class DeterministicInvariantCompiler:
    """Compile only facts derivable from action text; ambiguity remains explicit."""

    _NUMBER = re.compile(
        r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>milliseconds?|msecs?|ms|seconds?|secs?|s|"
        r"minutes?|mins?|%|percent|attempts?|retries?|items?|workers?)?",
        re.IGNORECASE,
    )
    _RUNTIME = re.compile(
        r"\b(confirm|prove|production|external|provider|operator|rehearsal|telemetry|p(?:50|90|95|99)|"
        r"historical|during the incident|contract portal|cluster events?)\b",
        re.IGNORECASE,
    )
    _TEST = re.compile(r"\b(test|regression|pytest|coverage|guard|ci)\b", re.IGNORECASE)
    _CODE = re.compile(
        r"\b(add|implement|enforce|route|return|use|gate|serve|remove|block|backpressure|reject|"
        r"fallback|circuit breaker|jitter|backoff|dlq|dead.?letter|idempotenc|readiness|liveness|"
        r"runbook|index|secret scan|alert)\w*\b",
        re.IGNORECASE,
    )
    _KEY_FAMILIES = {
        "retr": ["max_retries", "retry_limit", "max_attempts", "attempts"],
        "attempt": ["max_attempts", "attempts", "retry_limit"],
        "timeout": ["timeout", "timeout_ms", "timeout_seconds", "request_timeout"],
        "deadline": ["deadline", "timeout", "timeout_ms", "timeout_seconds"],
        "queue": ["queue_capacity", "maxsize", "max_size", "capacity"],
        "capacity": ["capacity", "max_capacity", "queue_capacity", "maxsize"],
        "concurrency": ["concurrency", "max_concurrency", "worker_limit"],
        "ttl": ["ttl", "retention", "retention_seconds"],
        "retention": ["retention", "ttl", "retention_seconds"],
        "threshold": ["threshold", "alert_threshold"],
        "alert": ["threshold", "alert_threshold", "for"],
        "rate": ["rate_limit", "requests_per_minute", "quota"],
    }

    def compile_action(self, action: ActionItem) -> CompilationResult:
        text = action.text.strip()
        invariant_id = stable_id("invariant", action.id, text)
        location = SourceLocation(line=action.source_line, section=action.source_section)

        if self._RUNTIME.search(text):
            reason = (
                "required runtime, external, or human context is not available in the repository"
            )
            invariant = CompiledInvariant(
                id=invariant_id,
                action_id=action.id,
                original_action=text,
                source_location=location,
                statement=f"Obtain independent evidence that: {text}",
                requirement_kind=RequirementKind.RUNTIME_CONTEXT,
                availability=RequirementAvailability.UNAVAILABLE,
                required_proof=["runtime or externally attested evidence"],
                unavailable_reason=reason,
            )
            return CompilationResult(
                [invariant],
                [self._unavailable_spec(invariant, DeterministicCheckType.RUNTIME_CONTEXT, reason)],
            )

        numeric = self._NUMBER.search(text)
        if numeric is not None:
            return self._compile_numeric(action, invariant_id, location, numeric)

        if self._TEST.search(text):
            invariant = CompiledInvariant(
                id=invariant_id,
                action_id=action.id,
                original_action=text,
                source_location=location,
                statement=f"An executable regression protection must assert the behavior: {text}",
                requirement_kind=RequirementKind.TEST_PROTECTION,
                required_proof=["located executable test", "behavioral assertion"],
            )
            spec = DeterministicCheckSpec(
                id=stable_id("check", invariant.id, "test_protection"),
                invariant_id=invariant.id,
                check_type=DeterministicCheckType.TEST_PROTECTION,
                description="Locate a test whose executable body contains a behavioral assertion",
                parameters={"query": text, "terms": self._meaningful_terms(text)},
            )
            return CompilationResult([invariant], [spec])

        if self._CODE.search(text):
            terms = self._meaningful_terms(text)
            if terms:
                invariant = CompiledInvariant(
                    id=invariant_id,
                    action_id=action.id,
                    original_action=text,
                    source_location=location,
                    statement=f"Executable code or configuration must implement: {text}",
                    requirement_kind=RequirementKind.CODE_STATIC,
                    required_proof=["executable implementation evidence", "regression protection"],
                )
                spec = DeterministicCheckSpec(
                    id=stable_id("check", invariant.id, "static_code"),
                    invariant_id=invariant.id,
                    check_type=DeterministicCheckType.STATIC_CODE,
                    description="Find the action's material terms in executable syntax",
                    parameters={"terms": terms},
                )
                return CompilationResult([invariant], [spec, self._protection_spec(invariant)])

        reason = "the action does not identify a supported measurable repository or runtime fact"
        invariant = CompiledInvariant(
            id=invariant_id,
            action_id=action.id,
            original_action=text,
            source_location=location,
            statement=f"Manual interpretation required: {text}",
            requirement_kind=RequirementKind.UNSUPPORTED,
            availability=RequirementAvailability.UNSUPPORTED,
            unavailable_reason=reason,
            required_proof=["manual requirement clarification"],
        )
        return CompilationResult(
            [invariant],
            [self._unavailable_spec(invariant, DeterministicCheckType.UNSUPPORTED, reason)],
        )

    def compile(self, actions: list[ActionItem]) -> CompilationResult:
        invariants: list[CompiledInvariant] = []
        specs: list[DeterministicCheckSpec] = []
        for action in actions:
            result = self.compile_action(action)
            invariants.extend(result.invariants)
            specs.extend(result.check_specs)
        return CompilationResult(invariants, specs)

    def _compile_numeric(
        self,
        action: ActionItem,
        invariant_id: str,
        location: SourceLocation,
        numeric: re.Match[str],
    ) -> CompilationResult:
        text = action.text.strip()
        value = float(numeric.group("value"))
        expected: int | float = int(value) if value.is_integer() else value
        unit = self._normalize_unit(numeric.group("unit"))
        operator = self._operator(text)
        key_candidates = self._key_candidates(text)
        available = bool(key_candidates)
        reason = (
            None
            if available
            else "numeric target is measurable but no supported config subject was identified"
        )
        availability = (
            RequirementAvailability.SUPPORTED if available else RequirementAvailability.UNSUPPORTED
        )
        relation = {
            CheckOperator.EQUALS: "equal",
            CheckOperator.LESS_THAN_OR_EQUAL: "at most",
            CheckOperator.GREATER_THAN_OR_EQUAL: "at least",
            CheckOperator.EXISTS: "present as",
        }[operator]
        unit_suffix = self._unit_suffix(unit)
        statement = f"The effective configured value must be {relation} {expected}{unit_suffix}"
        invariant = CompiledInvariant(
            id=invariant_id,
            action_id=action.id,
            original_action=text,
            source_location=location,
            statement=statement,
            requirement_kind=RequirementKind.NUMERIC_CONFIGURATION,
            availability=availability,
            expected_value=expected,
            unit=unit,
            required_proof=["effective configuration or code constant", "regression protection"],
            unavailable_reason=reason,
        )
        spec = DeterministicCheckSpec(
            id=stable_id("check", invariant.id, "configuration_value"),
            invariant_id=invariant.id,
            check_type=(
                DeterministicCheckType.CONFIGURATION_VALUE
                if available
                else DeterministicCheckType.UNSUPPORTED
            ),
            operator=operator,
            description="Compare every matching effective value with the action threshold",
            expected=expected,
            unit=unit,
            availability=availability,
            parameters={"key_candidates": key_candidates},
            unavailable_reason=reason,
        )
        return CompilationResult([invariant], [spec, self._protection_spec(invariant)])

    @staticmethod
    def _operator(text: str) -> CheckOperator:
        lowered = text.lower()
        if re.search(
            r"\b(at most|no more than|maximum|max|bound|bounded|cap|limit|within)\b", lowered
        ):
            return CheckOperator.LESS_THAN_OR_EQUAL
        if re.search(r"\b(at least|minimum|min|above|exceed)\b", lowered):
            return CheckOperator.GREATER_THAN_OR_EQUAL
        return CheckOperator.EQUALS

    @staticmethod
    def _normalize_unit(unit: str | None) -> str | None:
        if unit is None:
            return None
        lowered = unit.lower()
        if lowered in {"millisecond", "milliseconds", "msec", "msecs", "ms"}:
            return "milliseconds"
        if lowered in {"second", "seconds", "sec", "secs", "s"}:
            return "seconds"
        if lowered in {"minute", "minutes", "min", "mins"}:
            return "minutes"
        if lowered in {"%", "percent"}:
            return "percent"
        if lowered.startswith("retr") or lowered.startswith("attempt"):
            return "attempts"
        return lowered

    def _key_candidates(self, text: str) -> list[str]:
        lowered = text.lower()
        candidates: list[str] = []
        for term, keys in self._KEY_FAMILIES.items():
            if term in lowered:
                candidates.extend(keys)
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _meaningful_terms(text: str) -> list[str]:
        stop = {
            "a",
            "an",
            "and",
            "add",
            "all",
            "at",
            "be",
            "for",
            "from",
            "in",
            "into",
            "is",
            "of",
            "on",
            "or",
            "the",
            "to",
            "use",
            "with",
            "while",
            "block",
            "create",
            "enable",
            "enforce",
            "implement",
            "remove",
            "return",
            "route",
            "serve",
            "validate",
        }
        terms = [
            token.lower()
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_-]+", text)
            if token.lower() not in stop and len(token) >= 3
        ]
        return list(dict.fromkeys(terms))[:8]

    @staticmethod
    def _unit_suffix(unit: str | None) -> str:
        return f" {unit}" if unit else ""

    @staticmethod
    def _unavailable_spec(
        invariant: CompiledInvariant,
        check_type: DeterministicCheckType,
        reason: str,
    ) -> DeterministicCheckSpec:
        availability = (
            RequirementAvailability.UNAVAILABLE
            if check_type == DeterministicCheckType.RUNTIME_CONTEXT
            else RequirementAvailability.UNSUPPORTED
        )
        return DeterministicCheckSpec(
            id=stable_id("check", invariant.id, check_type.value),
            invariant_id=invariant.id,
            check_type=check_type,
            description="No deterministic repository check is available",
            availability=availability,
            unavailable_reason=reason,
        )

    @staticmethod
    def _protection_spec(invariant: CompiledInvariant) -> DeterministicCheckSpec:
        return DeterministicCheckSpec(
            id=stable_id("check", invariant.id, "regression_protection"),
            invariant_id=invariant.id,
            check_type=DeterministicCheckType.TEST_PROTECTION,
            description="Locate regression protection for the compiled requirement",
            core=False,
            parameters={
                "query": invariant.original_action,
                "terms": DeterministicInvariantCompiler._meaningful_terms(
                    invariant.original_action
                ),
            },
        )
