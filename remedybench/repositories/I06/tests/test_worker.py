from worker import queue_depth


def test_queue_depth_regression() -> None:
    assert queue_depth() <= 500
