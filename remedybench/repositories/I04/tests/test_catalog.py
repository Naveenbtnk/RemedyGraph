from catalog import recover_half_open


def test_half_open_recovery() -> None:
    assert recover_half_open() is True
