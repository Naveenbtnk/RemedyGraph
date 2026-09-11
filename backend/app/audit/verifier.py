"""Conservative action-level verdict aggregation."""

from collections.abc import Sequence

from backend.app.audit.contracts import (
    ActionVerdict,
    CheckOutcome,
    CompiledInvariant,
    DeterministicCheckResult,
    EvidenceCitation,
    EvidenceRecord,
    EvidenceRole,
    RequirementKind,
)
from backend.app.ids import stable_id
from backend.app.models import ActionItem, EvidenceKind, Verdict


class VerdictEngine:
    """Apply deterministic constraints before any semantic interpretation."""

    _CREDIBLE_IMPLEMENTATION = {
        EvidenceKind.CODE,
        EvidenceKind.CONFIGURATION,
        EvidenceKind.TEST,
        EvidenceKind.EXECUTION,
    }

    def verify_action(
        self,
        *,
        run_id: str,
        action: ActionItem,
        invariants: Sequence[CompiledInvariant],
        results: Sequence[DeterministicCheckResult],
        evidence: Sequence[EvidenceRecord],
    ) -> ActionVerdict:
        invariant_ids = [item.id for item in invariants]
        relevant_results = [item for item in results if item.invariant_id in invariant_ids]
        relevant_evidence = [item for item in evidence if item.invariant_id in invariant_ids]
        citations = self._citations(relevant_evidence)
        missing: list[str] = []

        failed = [
            item
            for item in relevant_results
            if item.core and item.outcome in {CheckOutcome.FAILED, CheckOutcome.NOT_FOUND}
        ]
        protection_gaps = [
            item
            for item in relevant_results
            if not item.core and item.outcome != CheckOutcome.PASSED
        ]
        non_assessable = [
            item
            for item in relevant_results
            if item.outcome
            in {CheckOutcome.UNAVAILABLE, CheckOutcome.UNSUPPORTED, CheckOutcome.ERROR}
        ]
        passed = [item for item in relevant_results if item.outcome == CheckOutcome.PASSED]
        supporting = [item for item in relevant_evidence if item.role == EvidenceRole.SUPPORTING]
        contradictory = [
            item for item in relevant_evidence if item.role == EvidenceRole.CONTRADICTORY
        ]
        test_only_requirement = bool(invariants) and all(
            item.requirement_kind == RequirementKind.TEST_PROTECTION for item in invariants
        )
        credible_kinds = set(self._CREDIBLE_IMPLEMENTATION)
        if not test_only_requirement:
            credible_kinds.discard(EvidenceKind.TEST)
        credible = [item for item in supporting if item.kind in credible_kinds]
        regression = any(item.kind == EvidenceKind.TEST for item in supporting)

        if failed:
            verdict = Verdict.MISSING
            missing.extend(item.detail for item in failed)
            rationale = (
                "A required deterministic implementation check failed or found no implementation."
            )
        elif relevant_results and len(non_assessable) == len(relevant_results):
            verdict = Verdict.UNVERIFIABLE
            missing.extend(item.detail for item in non_assessable)
            rationale = (
                "The required fact cannot be assessed with the available repository or runtime "
                "context."
            )
        elif passed and credible and regression and not contradictory and not non_assessable:
            verdict = Verdict.VERIFIED
            rationale = (
                "All required deterministic checks pass with implementation and "
                "regression evidence."
            )
        elif passed or credible:
            verdict = Verdict.PARTIAL
            if not regression:
                missing.append("adequate regression protection is absent")
            missing.extend(item.detail for item in non_assessable)
            missing.extend(item.detail for item in protection_gaps)
            if contradictory:
                missing.append("contradictory evidence remains unresolved")
            rationale = (
                "Some implementation or protection is present, but required proof is incomplete."
            )
        else:
            verdict = Verdict.MISSING
            missing.append("no credible implementation evidence was found")
            rationale = "No credible implementation or deterministic protection was found."

        missing = list(dict.fromkeys(item for item in missing if item))
        if not citations and not missing:
            missing.append("no citable evidence was produced")
        return ActionVerdict(
            id=stable_id("verdict", run_id, action.id),
            run_id=run_id,
            action_id=action.id,
            verdict=verdict,
            rationale=rationale,
            invariant_ids=invariant_ids,
            citations=citations,
            missing_proofs=missing,
            confidence=1.0 if verdict in {Verdict.MISSING, Verdict.UNVERIFIABLE} else 0.9,
        )

    @staticmethod
    def assessed_coverage(verdicts: Sequence[ActionVerdict]) -> float:
        if not verdicts:
            return 0.0
        weights = {
            Verdict.VERIFIED: 1.0,
            Verdict.PARTIAL: 0.5,
            Verdict.MISSING: 0.0,
            Verdict.UNVERIFIABLE: 0.0,
        }
        return round(sum(weights[item.verdict] for item in verdicts) / len(verdicts) * 100, 2)

    @staticmethod
    def _citations(evidence: Sequence[EvidenceRecord]) -> list[EvidenceCitation]:
        result: list[EvidenceCitation] = []
        seen: set[str] = set()
        for item in evidence:
            if item.id in seen or item.role not in {
                EvidenceRole.SUPPORTING,
                EvidenceRole.CONTRADICTORY,
            }:
                continue
            seen.add(item.id)
            result.append(item.citation())
        return result
