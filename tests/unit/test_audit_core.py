from pathlib import Path

import pytest

from backend.app.audit.budget import BudgetExceeded, BudgetTracker
from backend.app.audit.checks import DeterministicCheckRunner
from backend.app.audit.compiler import DeterministicInvariantCompiler
from backend.app.audit.contracts import (
    BudgetUsage,
    CheckOutcome,
    DeterministicCheckResult,
    DeterministicCheckSpec,
    DeterministicCheckType,
    EvidenceRecord,
    EvidenceRole,
    RequirementAvailability,
    RequirementKind,
)
from backend.app.audit.verifier import VerdictEngine
from backend.app.models import ActionItem, EvidenceKind, Verdict


def action(text: str, *, action_id: str = "action_1") -> ActionItem:
    return ActionItem(
        id=action_id,
        incident_id="incident_1",
        text=text,
        source_line=17,
        source_section="Corrective actions",
        order=0,
    )


@pytest.mark.parametrize(
    ("text", "kind", "check_type", "availability"),
    [
        (
            "Bound retries to 3",
            RequirementKind.NUMERIC_CONFIGURATION,
            DeterministicCheckType.CONFIGURATION_VALUE,
            RequirementAvailability.SUPPORTED,
        ),
        (
            "Add exponential backoff with jitter",
            RequirementKind.CODE_STATIC,
            DeterministicCheckType.STATIC_CODE,
            RequirementAvailability.SUPPORTED,
        ),
        (
            "Add a regression test for retry exhaustion",
            RequirementKind.TEST_PROTECTION,
            DeterministicCheckType.TEST_PROTECTION,
            RequirementAvailability.SUPPORTED,
        ),
        (
            "Confirm production gateway deadline",
            RequirementKind.RUNTIME_CONTEXT,
            DeterministicCheckType.RUNTIME_CONTEXT,
            RequirementAvailability.UNAVAILABLE,
        ),
        (
            "Make things better",
            RequirementKind.UNSUPPORTED,
            DeterministicCheckType.UNSUPPORTED,
            RequirementAvailability.UNSUPPORTED,
        ),
    ],
)
def test_compiler_selects_explicit_requirement_types(
    text: str,
    kind: RequirementKind,
    check_type: DeterministicCheckType,
    availability: RequirementAvailability,
) -> None:
    result = DeterministicInvariantCompiler().compile_action(action(text))

    invariant = result.invariants[0]
    assert invariant.original_action == text
    assert invariant.source_location.line == 17
    assert invariant.source_location.section == "Corrective actions"
    assert invariant.requirement_kind == kind
    assert invariant.availability == availability
    assert result.check_specs[0].check_type == check_type
    if availability != RequirementAvailability.SUPPORTED:
        assert invariant.unavailable_reason
        assert result.check_specs[0].unavailable_reason


def test_numeric_compiler_preserves_threshold_and_adds_regression_check() -> None:
    result = DeterministicInvariantCompiler().compile_action(action("Bound retries to 3"))

    assert result.invariants[0].expected_value == 3
    assert result.invariants[0].unit is None
    assert [spec.check_type for spec in result.check_specs] == [
        DeterministicCheckType.CONFIGURATION_VALUE,
        DeterministicCheckType.TEST_PROTECTION,
    ]


def test_failed_deterministic_check_cannot_be_upgraded(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    (repository / "tests").mkdir(parents=True)
    (repository / "settings.yaml").write_text("retry:\n  limit: 4\n", encoding="utf-8")
    (repository / "tests" / "test_retry.py").write_text(
        "def test_retry_exhaustion_is_bounded():\n    assert 4 == 4\n", encoding="utf-8"
    )
    item = action("Bound retries to 3")
    compiled = DeterministicInvariantCompiler().compile_action(item)
    runner = DeterministicCheckRunner(tmp_path, repository)
    executions = [
        runner.run(spec, run_id="run_1", action_id=item.id) for spec in compiled.check_specs
    ]

    assert executions[0].result.outcome == CheckOutcome.FAILED
    assert executions[1].result.outcome == CheckOutcome.NOT_FOUND
    verdict = VerdictEngine().verify_action(
        run_id="run_1",
        action=item,
        invariants=compiled.invariants,
        results=[execution.result for execution in executions],
        evidence=[record for execution in executions for record in execution.evidence],
    )
    assert verdict.verdict == Verdict.MISSING
    assert verdict.citations


def test_unused_circuit_breaker_and_constant_assertion_are_never_verified(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    (repository / "tests").mkdir(parents=True)
    (repository / "circuit.py").write_text("class CircuitBreaker:\n    pass\n", encoding="utf-8")
    (repository / "tests" / "test_circuit.py").write_text(
        """from math import sqrt

def test_circuit_breaker():
    assert True

def test_circuit_breaker_unrelated_behavior():
    assert sqrt(4) == 2
""",
        encoding="utf-8",
    )
    item = action("Add a circuit breaker")
    compiled = DeterministicInvariantCompiler().compile_action(item)
    runner = DeterministicCheckRunner(tmp_path, repository)
    executions = [
        runner.run(spec, run_id="run_1", action_id=item.id) for spec in compiled.check_specs
    ]

    assert [execution.result.outcome for execution in executions] == [
        CheckOutcome.NOT_FOUND,
        CheckOutcome.NOT_FOUND,
    ]
    verdict = VerdictEngine().verify_action(
        run_id="run_1",
        action=item,
        invariants=compiled.invariants,
        results=[execution.result for execution in executions],
        evidence=[record for execution in executions for record in execution.evidence],
    )
    assert verdict.verdict in {Verdict.MISSING, Verdict.PARTIAL}
    assert verdict.verdict != Verdict.VERIFIED


def test_static_python_requires_use_not_names_strings_comments_or_disabled_config(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    source = repository / "circuit.py"
    source.write_text(
        """# circuit breaker
class CircuitBreaker:
    pass

circuit_breaker_name = "circuit breaker"
""",
        encoding="utf-8",
    )
    (repository / "settings.yaml").write_text("circuit_breaker: false\n", encoding="utf-8")
    item = action("Add a circuit breaker")
    compiled = DeterministicInvariantCompiler().compile_action(item)
    runner = DeterministicCheckRunner(tmp_path, repository)

    absent = runner.run(compiled.check_specs[0], run_id="run_1", action_id=item.id)
    assert absent.result.outcome == CheckOutcome.NOT_FOUND

    source.write_text(
        """class CircuitBreaker:
    pass

def register(component: object) -> None:
    pass

register(CircuitBreaker)
""",
        encoding="utf-8",
    )
    wired = runner.run(compiled.check_specs[0], run_id="run_1", action_id=item.id)
    assert wired.result.outcome == CheckOutcome.PASSED
    assert {record.metadata.get("proof_kind") for record in wired.evidence} == {"wiring"}


def test_bounded_static_pattern_is_supporting_only_and_never_executes_command(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "README.md").write_text("marker: circuit-breaker\n", encoding="utf-8")
    item = action("Add a circuit breaker")
    invariant = DeterministicInvariantCompiler().compile_action(item).invariants[0]
    marker = tmp_path / "must-not-exist"
    spec = DeterministicCheckSpec(
        id="check_pattern",
        invariant_id=invariant.id,
        check_type=DeterministicCheckType.STATIC_PATTERN,
        description="bounded literal scan",
        parameters={
            "literal_pattern": "circuit-breaker",
            "command": f"touch {marker}",
        },
    )

    execution = DeterministicCheckRunner(tmp_path, repository).run(
        spec, run_id="run_1", action_id=item.id
    )

    assert execution.result.outcome == CheckOutcome.PASSED
    assert all(record.role == EvidenceRole.SUPPORTING_ONLY for record in execution.evidence)
    assert not marker.exists()


def test_budget_tracker_allows_exact_limits_and_rejects_next_work() -> None:
    tracker = BudgetTracker(BudgetUsage(model_calls_limit=6, investigation_round_limit=3))
    for _ in range(6):
        tracker.consume_model_call()
    for _ in range(3):
        tracker.consume_investigation_round("invariant_1")

    with pytest.raises(BudgetExceeded, match="model call"):
        tracker.consume_model_call()
    with pytest.raises(BudgetExceeded, match="investigation round"):
        tracker.consume_investigation_round("invariant_1")


@pytest.mark.parametrize("kind", [EvidenceKind.DOCUMENT, EvidenceKind.GIT])
def test_document_or_git_only_support_cannot_produce_verified(kind: EvidenceKind) -> None:
    item = action("Add a circuit breaker")
    compiled = DeterministicInvariantCompiler().compile_action(item)
    invariant = compiled.invariants[0]
    result = DeterministicCheckResult(
        id="result_1",
        run_id="run_1",
        invariant_id=invariant.id,
        check_spec_id=compiled.check_specs[0].id,
        outcome=CheckOutcome.PASSED,
        passed=True,
        detail="synthetic deterministic result",
    )
    evidence = EvidenceRecord(
        id="evidence_1",
        run_id="run_1",
        action_id=item.id,
        invariant_id=invariant.id,
        kind=kind,
        role=EvidenceRole.SUPPORTING_ONLY,
        source_path="README.md" if kind == EvidenceKind.DOCUMENT else None,
        line_start=1 if kind == EvidenceKind.DOCUMENT else None,
        line_end=1 if kind == EvidenceKind.DOCUMENT else None,
        excerpt="the fix was shipped",
    )

    verdict = VerdictEngine().verify_action(
        run_id="run_1",
        action=item,
        invariants=compiled.invariants,
        results=[result],
        evidence=[evidence],
    )

    assert verdict.verdict != Verdict.VERIFIED
    assert verdict.missing_proofs
