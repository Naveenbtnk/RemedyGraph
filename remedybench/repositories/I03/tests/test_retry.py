from retry import capped_exponential_backoff


def test_capped_exponential_backoff_with_jitter() -> None:
    assert capped_exponential_backoff() <= 8.0
