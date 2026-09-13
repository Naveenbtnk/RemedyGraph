from payments import PAYMENT_TIMEOUT_SECONDS


def test_payment_timeout() -> None:
    assert PAYMENT_TIMEOUT_SECONDS == 5
