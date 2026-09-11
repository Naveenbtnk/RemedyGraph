"""Deterministic, template-owned guard preview generation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence

from backend.app.audit.contracts import (
    AuditWorkflowState,
    DeterministicCheckSpec,
    DeterministicCheckType,
)
from backend.app.guards.contracts import GuardSpec, GuardType
from backend.app.ids import stable_id
from backend.app.models import Verdict

TEMPLATE_VERSION = "guard-v1"
_SAFE_TERM = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")


class GuardGenerator:
    """Create safe previews only for incomplete, assessable corrective actions."""

    def generate(self, state: AuditWorkflowState) -> list[GuardSpec]:
        action_by_id = {item.id: item for item in state.actions}
        invariant_by_id = {item.id: item for item in state.invariants}
        specs_by_invariant = {
            invariant.id: [spec for spec in state.check_specs if spec.invariant_id == invariant.id]
            for invariant in state.invariants
        }
        guards: list[GuardSpec] = []
        for verdict in state.verdicts:
            if verdict.verdict not in {Verdict.PARTIAL, Verdict.MISSING}:
                continue
            action = action_by_id.get(verdict.action_id)
            if action is None:
                continue
            for invariant_id in verdict.invariant_ids[:1]:
                invariant = invariant_by_id.get(invariant_id)
                if invariant is None or invariant.unavailable_reason:
                    continue
                specs = specs_by_invariant[invariant_id]
                guard_type, terms, test_only, match_all, expected_literals = self._strategy(
                    action.text, specs, verdict=verdict.verdict
                )
                if not terms:
                    continue
                guard_id = stable_id(
                    "guard", state.summary.id, action.id, invariant.id, TEMPLATE_VERSION
                )
                target = f".remedygraph/generated_guards/{state.summary.id}/{guard_id}.py"
                preview = self.render(
                    terms,
                    guard_type=guard_type,
                    test_only=test_only,
                    match_all=match_all,
                    expected_literals=expected_literals,
                )
                guards.append(
                    GuardSpec(
                        id=guard_id,
                        run_id=state.summary.id,
                        action_id=action.id,
                        invariant_id=invariant.id,
                        name=f"Protect: {action.text[:72]}",
                        guard_type=guard_type,
                        intent=f"Detect regression of corrective action: {action.text}",
                        assumptions=[
                            "The repository remains readable from the approved local workspace.",
                            "Promotion into project tests remains a separate manual operation.",
                        ],
                        assertions=[
                            f"Structural repository evidence contains: {term}" for term in terms
                        ],
                        target_path=target,
                        preview=preview,
                        preview_sha256=hashlib.sha256(preview.encode("utf-8")).hexdigest(),
                        template_version=TEMPLATE_VERSION,
                        terms=terms,
                        test_only=test_only,
                        match_all=match_all,
                        expected_literals=expected_literals,
                    )
                )
        return guards

    def _strategy(
        self,
        action_text: str,
        specs: Sequence[DeterministicCheckSpec],
        *,
        verdict: Verdict,
    ) -> tuple[GuardType, list[str], bool, bool, list[str]]:
        raw_terms: list[str] = []
        guard_type = GuardType.STATIC_REPOSITORY
        test_only = False
        match_all = True
        expected_literals: list[str] = []
        selected = list(specs)
        if verdict == Verdict.MISSING:
            implementation = [
                spec for spec in specs if spec.check_type != DeterministicCheckType.TEST_PROTECTION
            ]
            selected = implementation or selected
        elif verdict == Verdict.PARTIAL:
            protection = [
                spec for spec in specs if spec.check_type == DeterministicCheckType.TEST_PROTECTION
            ]
            selected = protection or selected
        for spec in selected:
            check_type = spec.check_type
            parameters = spec.parameters
            if check_type == DeterministicCheckType.TEST_PROTECTION:
                guard_type = GuardType.TEST_PROTECTION
                test_only = True
            elif check_type == DeterministicCheckType.CONFIGURATION_VALUE:
                guard_type = GuardType.CONFIGURATION
                match_all = False
                if spec.expected is not None:
                    expected_literals.append(str(spec.expected).casefold())
            values = parameters.get("terms") or parameters.get("key_candidates") or []
            raw_terms.extend(str(value) for value in values)
        if not raw_terms:
            raw_terms = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", action_text)
        terms: list[str] = []
        for term in raw_terms:
            normalized = term.strip().casefold()
            if _SAFE_TERM.fullmatch(normalized) and normalized not in terms:
                terms.append(normalized)
            if len(terms) == 6:
                break
        return guard_type, terms, test_only, match_all, expected_literals[:3]

    @staticmethod
    def render(
        terms: list[str],
        *,
        guard_type: GuardType,
        test_only: bool,
        match_all: bool,
        expected_literals: list[str],
    ) -> str:
        extensions = [".py"] if test_only else [".py", ".json", ".toml", ".yaml", ".yml"]
        return (
            '"""Generated by RemedyGraph; execute only after explicit approval."""\n'
            "import ast\n"
            "from pathlib import Path\n\n"
            f"TERMS = {json.dumps(terms)}\n"
            f"EXPECTED_LITERALS = {json.dumps(expected_literals)}\n"
            f"EXTENSIONS = {json.dumps(extensions)}\n"
            f"TEST_ONLY = {test_only!r}\n"
            f"MATCH_ALL = {match_all!r}\n"
            f"GUARD_TYPE = {json.dumps(guard_type.value)}\n"
            "ROOT = Path.cwd().resolve()\n"
            "EXCLUDED = {'.git', '.remedygraph', '.venv', 'node_modules', 'dist', 'build'}\n\n"
            "def eligible(path: Path) -> bool:\n"
            "    relative = path.relative_to(ROOT)\n"
            "    allowed = path.suffix in EXTENSIONS\n"
            "    outside_excluded = not any(part in EXCLUDED for part in relative.parts)\n"
            "    test_path = path.name.startswith('test_') or 'tests' in relative.parts\n"
            "    return allowed and outside_excluded and (not TEST_ONLY or test_path)\n\n"
            "def python_facts(path: Path) -> tuple[str, bool]:\n"
            "    try:\n"
            "        tree = ast.parse(path.read_text(encoding='utf-8', errors='ignore'))\n"
            "    except SyntaxError:\n"
            "        return '', False\n"
            "    names = []\n"
            "    has_behavioral_assert = False\n"
            "    for node in ast.walk(tree):\n"
            "        if TEST_ONLY and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):\n"
            "            names.append(node.name.casefold())\n"
            "        if isinstance(node, ast.Call):\n"
            "            names.append(ast.unparse(node.func).casefold())\n"
            "        if TEST_ONLY and isinstance(node, ast.Assert):\n"
            "            if not isinstance(node.test, ast.Constant):\n"
            "                has_behavioral_assert = True\n"
            "    return ' '.join(names), has_behavioral_assert\n\n"
            "facts = []\n"
            "behavioral_assertion = False\n"
            "for path in ROOT.rglob('*'):\n"
            "    if not path.is_file() or not eligible(path):\n"
            "        continue\n"
            "    if path.suffix == '.py':\n"
            "        value, asserted = python_facts(path)\n"
            "        facts.append(value)\n"
            "        behavioral_assertion = behavioral_assertion or asserted\n"
            "    elif GUARD_TYPE == 'configuration':\n"
            "        lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()\n"
            "        active = [line for line in lines if not line.lstrip().startswith('#')]\n"
            "        facts.append(' '.join(active).casefold())\n"
            "content = ' '.join(facts)\n"
            "if MATCH_ALL:\n"
            "    term_match = all(term in content for term in TERMS)\n"
            "else:\n"
            "    term_match = any(term in content for term in TERMS)\n"
            "literal_match = all(item in content for item in EXPECTED_LITERALS)\n"
            "structure_match = behavioral_assertion if TEST_ONLY else True\n"
            "if not (term_match and literal_match and structure_match):\n"
            "    print('guard failed: required structural evidence is absent')\n"
            "    raise SystemExit(1)\n"
            "print('guard passed: required structural evidence is present')\n"
        )
