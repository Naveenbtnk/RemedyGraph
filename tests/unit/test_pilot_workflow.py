import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
FULL_ACTION_REF = re.compile(r"^[^\s@]+@[a-f0-9]{40}(?:\s+#.*)?$")


def test_pilot_workflow_is_manual_read_only_and_pins_external_actions() -> None:
    path = ROOT / ".github" / "workflows" / "pilot-audit.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    assert workflow["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "persist-credentials: false" in text
    assert "timeout-minutes: 10" in text
    assert "retention-days: 7" in text
    for reference in re.findall(r"^\s*-?\s*uses:\s*(.+)$", text, re.MULTILINE):
        if reference.strip() != "./":
            assert FULL_ACTION_REF.fullmatch(reference.strip())


def test_composite_action_does_not_interpolate_inputs_into_shell_script() -> None:
    text = (ROOT / "action.yml").read_text(encoding="utf-8")
    run_blocks = re.findall(r"\n\s+run:\s*\|\n((?:\s{8}.*\n?)*)", text)

    assert run_blocks
    assert all("${{ inputs." not in block for block in run_blocks)
    assert "REMEDYGRAPH_INPUT_POSTMORTEM: ${{ inputs.postmortem }}" in text
    assert "REMEDYGRAPH_INPUT_REPOSITORY: ${{ inputs.repository }}" in text
    assert "REMEDYGRAPH_INPUT_OUTPUT: ${{ inputs.output }}" in text
