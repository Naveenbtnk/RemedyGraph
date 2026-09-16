import shutil
from pathlib import Path

from backend.app.evaluation.contracts import EvaluationReport
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

    saved = EvaluationReport.model_validate_json(
        (root / "evals/results/remedybench-smoke.json").read_text(encoding="utf-8")
    )
    assert saved.metadata.worktree_dirty is False
    assert saved.metadata.benchmark_sha256 == report.metadata.benchmark_sha256
    assert saved.metrics.model_dump(exclude={"p50_duration_ms", "p95_duration_ms"}) == (
        report.metrics.model_dump(exclude={"p50_duration_ms", "p95_duration_ms"})
    )
    assert [case.model_dump(exclude={"duration_ms"}) for case in saved.cases] == [
        case.model_dump(exclude={"duration_ms"}) for case in report.cases
    ]


def test_remedybench_contains_all_four_verdict_classes() -> None:
    root = Path(__file__).parents[2]
    evaluator = RemedyBenchEvaluator(root / "remedybench", repository_root=root)
    verdicts = {
        action.verdict.value for case in evaluator.manifest.cases for action in case.actions
    }

    assert verdicts == {"VERIFIED", "PARTIAL", "MISSING", "UNVERIFIABLE"}
    assert evaluator.manifest.provenance.synthetic is True


def test_benchmark_hash_is_independent_of_checkout_line_endings(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    benchmark = root / "remedybench"
    copied = tmp_path / "remedybench"
    shutil.copytree(benchmark, copied)
    for path in copied.rglob("*"):
        if path.is_file():
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))

    benchmark_hash = RemedyBenchEvaluator(benchmark)._benchmark_hash()
    assert benchmark_hash == RemedyBenchEvaluator(copied)._benchmark_hash()
    # Frozen v0.1.0 fixtures must hash identically on Windows and Linux.
    assert benchmark_hash == "7976ae3d5c3d19276f33ed209425d70bc95a2e5ae2557d731511efbf8cb6ad7e"


def test_benchmark_hash_ignores_runtime_guard_artifacts(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    benchmark = root / "remedybench"
    copied = tmp_path / "remedybench"
    shutil.copytree(benchmark, copied, ignore=shutil.ignore_patterns(".remedygraph"))
    before = RemedyBenchEvaluator(copied)._benchmark_hash()
    runtime = copied / "repositories" / "I04" / ".remedygraph" / "generated_guards"
    runtime.mkdir(parents=True)
    (runtime / "guard.py").write_text("raise SystemExit(1)\n", encoding="utf-8")

    assert RemedyBenchEvaluator(copied)._benchmark_hash() == before
