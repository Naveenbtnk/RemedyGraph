from payments.retry import MAX_RETRY_ATTEMPTS


def test_payment_retries_are_bounded_to_three_attempts():
    assert MAX_RETRY_ATTEMPTS == 3
