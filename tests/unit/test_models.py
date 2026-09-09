import pytest
from pydantic import ValidationError

from backend.app.models import ActionItem, Verdict


def test_domain_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ActionItem(id="a", incident_id="i", text="action", order=0, unexpected=True)


def test_verdict_values_are_stable() -> None:
    assert [verdict.value for verdict in Verdict] == [
        "VERIFIED",
        "PARTIAL",
        "MISSING",
        "UNVERIFIABLE",
    ]
