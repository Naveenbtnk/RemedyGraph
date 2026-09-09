from backend.app.llm.base import GenerationRequest
from backend.app.llm.mock import MockLLMProvider
from backend.app.models import ActionExtraction


def test_mock_provider_splits_compound_actions_without_network() -> None:
    result = MockLLMProvider().generate(
        GenerationRequest(
            task="extract_actions",
            input_text="""# Payment retry storm

## Corrective actions
- Bound retries to 3 and add exponential backoff with jitter.
- Add a regression test for retry exhaustion.
""",
        ),
        ActionExtraction,
    )

    assert [action.text for action in result.actions] == [
        "Bound retries to 3",
        "add exponential backoff with jitter",
        "Add a regression test for retry exhaustion",
    ]
    assert result.actions[0].source_line == 4


def test_mock_provider_rejects_unknown_task() -> None:
    request = GenerationRequest(task="verify", input_text="anything")
    try:
        MockLLMProvider().generate(request, ActionExtraction)
    except ValueError as exc:
        assert "does not support task" in str(exc)
    else:
        raise AssertionError("unknown mock tasks must fail explicitly")
