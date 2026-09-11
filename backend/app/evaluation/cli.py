"""Command-line entry point for reproducible RemedyBench evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.app.evaluation.runner import RemedyBenchEvaluator


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic RemedyBench smoke set")
    parser.add_argument("--benchmark", type=Path, default=Path("remedybench"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repository-commit")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    evaluator = RemedyBenchEvaluator(arguments.benchmark, repository_root=Path.cwd())
    report = evaluator.run(repository_commit=arguments.repository_commit)
    payload = report.model_dump_json(indent=2)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    if arguments.check:
        metrics = report.metrics
        safe = (
            metrics.action_extraction_f1 >= 0.85
            and metrics.evidence_recall_at_5 >= 0.80
            and metrics.citation_accuracy >= 0.90
            and metrics.verification_macro_f1 >= 0.75
            and metrics.unsupported_verified_rate == 0.0
            and metrics.documentation_only_verified_rate == 0.0
            and metrics.guard_runnable_rate >= 0.75
            and metrics.guard_detection_rate >= 0.75
            and metrics.average_model_calls_per_incident <= 6
        )
        return 0 if safe else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
