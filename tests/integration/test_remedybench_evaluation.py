from pathlib import Path

from backend.app.evaluation.runner import RemedyBenchEvaluator


def test_remedybench_smoke_is_reproducible_and_conservative() -> None:
    root = Path(__file__).parents[2]
    report = RemedyBenchEvaluator(root / "remedybench", repository_root=root).run(
        repository_commit="test-revision"
    )

    assert report.metrics.cases == 5
    assert report.metrics.gold_actions == 15
    assert report.metrics.action_extraction_f1 == 1.0
    assert report.metrics.evidence_recall_at_5 == 1.0
    assert report.metrics.verification_accuracy == 1.0
    assert report.metrics.verification_macro_f1 == 1.0
    assert report.metrics.unsupported_verified_rate == 0.0
    assert report.metrics.documentation_only_verified_rate == 0.0
    assert report.metrics.guard_runnable_rate == 1.0
    assert report.metrics.guard_detection_rate == 1.0
    assert report.metrics.average_model_calls_per_incident == 1.0


def test_remedybench_contains_all_four_verdict_classes() -> None:
    root = Path(__file__).parents[2]
    evaluator = RemedyBenchEvaluator(root / "remedybench", repository_root=root)
    verdicts = {
        action.verdict.value for case in evaluator.manifest.cases for action in case.actions
    }

    assert verdicts == {"VERIFIED", "PARTIAL", "MISSING", "UNVERIFIABLE"}
    assert evaluator.manifest.provenance.synthetic is True
