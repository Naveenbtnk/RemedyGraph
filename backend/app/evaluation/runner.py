"""Run the synthetic RemedyBench smoke set through the real local audit pipeline."""

from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from backend.app.audit.workflow import AuditWorkflow
from backend.app.evaluation.contracts import (
    ActionPrediction,
    BenchmarkManifest,
    CaseEvaluation,
    EvaluationMetadata,
    EvaluationMetrics,
    EvaluationReport,
    GoldAction,
)
from backend.app.guards.generator import GuardGenerator
from backend.app.guards.runner import GuardRunner, GuardSafetyError
from backend.app.ids import stable_id
from backend.app.llm.mock import MockLLMProvider
from backend.app.models import Verdict
from backend.app.schemas import IncidentCreate, ProjectCreate
from backend.app.services import IncidentService, ProjectService
from backend.app.settings import Settings
from backend.app.storage import SQLiteStore


class BenchmarkContractError(ValueError):
    """Raised when a benchmark fixture does not satisfy the frozen smoke contract."""


class RemedyBenchEvaluator:
    def __init__(self, benchmark_root: Path, *, repository_root: Path | None = None) -> None:
        self.benchmark_root = benchmark_root.resolve()
        self.repository_root = (repository_root or benchmark_root.parent).resolve()
        self.manifest = BenchmarkManifest.model_validate_json(
            (self.benchmark_root / "manifest.json").read_text(encoding="utf-8")
        )
        self._validate_manifest()

    def run(self, *, repository_commit: str | None = None) -> EvaluationReport:
        started_at = datetime.now(UTC)
        case_results: list[CaseEvaluation] = []
        with tempfile.TemporaryDirectory(prefix="remedybench-") as temporary:
            workspace = Path(temporary).resolve()
            for case in self.manifest.cases:
                case_results.append(self._run_case(case.id, workspace))
        completed_at = datetime.now(UTC)
        benchmark_hash = self._benchmark_hash()
        commit = repository_commit or self._git("rev-parse", "HEAD")
        dirty = bool(self._git("status", "--porcelain"))
        return EvaluationReport(
            metadata=EvaluationMetadata(
                evaluation_id=stable_id(
                    "evaluation", self.manifest.benchmark_version, benchmark_hash, commit
                ),
                repository_commit=commit,
                worktree_dirty=dirty,
                benchmark_version=self.manifest.benchmark_version,
                benchmark_sha256=benchmark_hash,
                provider="mock",
                model="deterministic-mock-v1",
                prompt_version=self.manifest.prompt_version,
                random_seed=0,
                retrieval_top_k=5,
                started_at=started_at,
                completed_at=completed_at,
            ),
            metrics=self._metrics(case_results),
            cases=case_results,
        )

    def _run_case(self, case_id: str, workspace: Path) -> CaseEvaluation:
        case = next(item for item in self.manifest.cases if item.id == case_id)
        source_repository = self._contained(self.benchmark_root / case.repository_path)
        incident_path = self._contained(self.benchmark_root / case.incident_path)
        target_repository = workspace / case.id
        shutil.copytree(source_repository, target_repository)
        settings = Settings(workspace_root=workspace, retrieval_top_k=5)
        store = SQLiteStore()
        started = time.perf_counter()
        try:
            project = ProjectService(store, workspace).create(
                ProjectCreate(name=case.id, repository_path=str(target_repository))
            )
            incident = IncidentService(store, MockLLMProvider(), settings.max_model_calls).create(
                IncidentCreate(
                    project_id=project.id,
                    source_name=incident_path.name,
                    source_text=incident_path.read_text(encoding="utf-8"),
                )
            )
            state = AuditWorkflow(store, settings).run(
                project, incident, run_id=f"eval_{case.id.lower()}"
            )
            if state.summary.status.value != "COMPLETE":
                raise BenchmarkContractError(f"{case.id} audit did not complete")
            predictions = [
                self._prediction(gold, case.id, state, workspace, target_repository)
                for gold in case.actions
            ]
            extracted = [action.text for action in state.actions]
            duration_ms = (time.perf_counter() - started) * 1000
            return CaseEvaluation(
                case_id=case.id,
                title=case.title,
                duration_ms=round(duration_ms, 3),
                model_calls=state.summary.budget.model_calls_used,
                extracted_actions=extracted,
                predictions=predictions,
            )
        finally:
            store.close()

    def _prediction(
        self,
        gold: GoldAction,
        case_id: str,
        state: object,
        workspace: Path,
        repository: Path,
    ) -> ActionPrediction:
        from backend.app.audit.contracts import AuditWorkflowState

        audit = AuditWorkflowState.model_validate(state)
        action = next(
            (
                item
                for item in audit.actions
                if self._normalize(item.text) == self._normalize(gold.text)
            ),
            None,
        )
        if action is None:
            return ActionPrediction(
                case_id=case_id,
                gold_action_id=gold.id,
                gold_text=gold.text,
                gold_verdict=gold.verdict,
                gold_requirement_kind=gold.requirement_kind,
            )
        invariant = next(item for item in audit.invariants if item.action_id == action.id)
        verdict = next(item for item in audit.verdicts if item.action_id == action.id)
        evidence_by_id = {item.id: item for item in audit.evidence}
        retrieved_paths: list[str] = []
        for item in audit.evidence:
            if (
                item.action_id != action.id
                or item.retrieval_score is None
                or item.source_path is None
            ):
                continue
            if item.source_path not in retrieved_paths:
                retrieved_paths.append(item.source_path)
            if len(retrieved_paths) == 5:
                break
        citation_paths = list(
            dict.fromkeys(
                item.source_path
                for citation in verdict.citations
                if (item := evidence_by_id[citation.evidence_id]).source_path is not None
            )
        )
        citation_kinds = list(
            dict.fromkeys(
                evidence_by_id[citation.evidence_id].kind.value for citation in verdict.citations
            )
        )
        guard = next(
            (item for item in GuardGenerator().generate(audit) if item.action_id == action.id), None
        )
        guard_status = None
        detected = None
        guard_type = None
        if guard is not None:
            guard_type = guard.guard_type
            runner = GuardRunner(workspace, repository, timeout_seconds=3, output_limit=4_096)
            try:
                runner.validate_preview(guard)
                runner.write_approved(guard)
                execution = runner.execute(guard)
                guard_status = execution.status
                detected = execution.status.value == "FAILED"
            except GuardSafetyError:
                detected = False
        return ActionPrediction(
            case_id=case_id,
            gold_action_id=gold.id,
            gold_text=gold.text,
            extracted_text=action.text,
            gold_verdict=gold.verdict,
            predicted_verdict=verdict.verdict,
            gold_requirement_kind=gold.requirement_kind,
            predicted_requirement_kind=invariant.requirement_kind,
            retrieved_paths_at_5=retrieved_paths,
            citation_paths=citation_paths,
            citation_kinds=citation_kinds,
            guard_type=guard_type,
            guard_status=guard_status,
            guard_detected_bad_state=detected,
        )

    def _metrics(self, cases: list[CaseEvaluation]) -> EvaluationMetrics:
        predictions = [prediction for case in cases for prediction in case.predictions]
        gold_count = len(predictions)
        extracted_count = sum(len(case.extracted_actions) for case in cases)
        matched = [item for item in predictions if item.extracted_text is not None]
        precision = self._ratio(len(matched), extracted_count)
        recall = self._ratio(len(matched), gold_count)
        extraction_f1 = self._f1(precision, recall)
        invariant_valid = sum(
            item.predicted_requirement_kind == item.gold_requirement_kind for item in matched
        )
        evidence_scored = [item for item in predictions if self._gold(item).gold_evidence_paths]
        evidence_hits = sum(
            bool(set(item.retrieved_paths_at_5) & set(self._gold(item).gold_evidence_paths))
            for item in evidence_scored
        )
        citation_total = sum(len(item.citation_paths) for item in predictions)
        citation_correct = sum(
            path in self._gold(item).acceptable_citation_paths
            for item in predictions
            for path in item.citation_paths
        )
        exact = sum(item.predicted_verdict == item.gold_verdict for item in predictions)
        per_class = {verdict.value: self._class_f1(predictions, verdict) for verdict in Verdict}
        verified_gold = [item for item in predictions if item.gold_verdict == Verdict.VERIFIED]
        predicted_verified = [
            item for item in predictions if item.predicted_verdict == Verdict.VERIFIED
        ]
        unsupported_verified = sum(
            item.predicted_requirement_kind is not None
            and item.predicted_requirement_kind.value in {"unsupported", "runtime_context"}
            for item in predicted_verified
        )
        documentation_only = sum(
            bool(item.citation_kinds) and set(item.citation_kinds) <= {"document", "git"}
            for item in predicted_verified
        )
        expected_guards = [item for item in predictions if self._gold(item).expected_guard_type]
        runnable = [item for item in expected_guards if item.guard_status is not None]
        durations = sorted(case.duration_ms for case in cases)
        return EvaluationMetrics(
            cases=len(cases),
            gold_actions=gold_count,
            extracted_actions=extracted_count,
            action_extraction_precision=precision,
            action_extraction_recall=recall,
            action_extraction_f1=extraction_f1,
            invariant_validity_rate=self._ratio(invariant_valid, len(matched)),
            evidence_recall_at_5=self._ratio(evidence_hits, len(evidence_scored)),
            citation_accuracy=self._ratio(citation_correct, citation_total),
            verification_accuracy=self._ratio(exact, gold_count),
            verification_macro_f1=round(sum(per_class.values()) / len(per_class), 4),
            verification_per_class_f1=per_class,
            false_positive_rate=self._ratio(
                sum(item.predicted_verdict != Verdict.VERIFIED for item in verified_gold),
                len(verified_gold),
            ),
            unsupported_verified_rate=self._ratio(unsupported_verified, len(predicted_verified)),
            documentation_only_verified_rate=self._ratio(
                documentation_only, len(predicted_verified)
            ),
            guard_type_accuracy=self._ratio(
                sum(
                    item.guard_type == self._gold(item).expected_guard_type
                    for item in expected_guards
                ),
                len(expected_guards),
            ),
            guard_runnable_rate=self._ratio(len(runnable), len(expected_guards)),
            guard_detection_rate=self._ratio(
                sum(item.guard_detected_bad_state is True for item in runnable), len(runnable)
            ),
            average_model_calls_per_incident=round(
                sum(case.model_calls for case in cases) / len(cases), 4
            ),
            p50_duration_ms=self._percentile(durations, 0.50),
            p95_duration_ms=self._percentile(durations, 0.95),
        )

    def _gold(self, prediction: ActionPrediction) -> GoldAction:
        case = next(item for item in self.manifest.cases if item.id == prediction.case_id)
        return next(item for item in case.actions if item.id == prediction.gold_action_id)

    def _validate_manifest(self) -> None:
        if not self.manifest.provenance.synthetic:
            raise BenchmarkContractError("RemedyBench smoke fixtures must be synthetic")
        case_ids = [case.id for case in self.manifest.cases]
        action_ids = [action.id for case in self.manifest.cases for action in case.actions]
        if len(case_ids) != len(set(case_ids)) or len(action_ids) != len(set(action_ids)):
            raise BenchmarkContractError("benchmark IDs must be unique")
        for case in self.manifest.cases:
            if not self._contained(self.benchmark_root / case.incident_path).is_file():
                raise BenchmarkContractError(f"missing incident fixture for {case.id}")
            if not self._contained(self.benchmark_root / case.repository_path).is_dir():
                raise BenchmarkContractError(f"missing repository fixture for {case.id}")

    def _benchmark_hash(self) -> str:
        digest = hashlib.sha256()
        paths = (item for item in self.benchmark_root.rglob("*") if item.is_file())
        for path in sorted(
            paths, key=lambda item: item.relative_to(self.benchmark_root).as_posix()
        ):
            relative = path.relative_to(self.benchmark_root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            # Git may materialize text fixtures with CRLF on Windows. Hash their
            # logical content so the same benchmark has one cross-platform ID.
            digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _contained(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.benchmark_root)
        except ValueError as exc:
            raise BenchmarkContractError("benchmark path escapes its root") from exc
        return resolved

    def _git(self, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            shell=False,
        )
        return completed.stdout.strip()

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().rstrip(".").split())

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    @staticmethod
    def _f1(precision: float, recall: float) -> float:
        return (
            round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
        )

    @classmethod
    def _class_f1(cls, predictions: list[ActionPrediction], verdict: Verdict) -> float:
        true_positive = sum(
            item.gold_verdict == verdict and item.predicted_verdict == verdict
            for item in predictions
        )
        false_positive = sum(
            item.gold_verdict != verdict and item.predicted_verdict == verdict
            for item in predictions
        )
        false_negative = sum(
            item.gold_verdict == verdict and item.predicted_verdict != verdict
            for item in predictions
        )
        precision = cls._ratio(true_positive, true_positive + false_positive)
        recall = cls._ratio(true_positive, true_positive + false_negative)
        return cls._f1(precision, recall)

    @staticmethod
    def _percentile(values: list[float], quantile: float) -> float:
        if not values:
            return 0.0
        index = max(0, math.ceil(quantile * len(values)) - 1)
        return round(values[index], 3)
