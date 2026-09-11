MAX_RETRIES = 3


def jitter() -> float:
    return 0.25


def backoff(value: float) -> float:
    return 2.0 + value


def exponential(value: float) -> float:
    return value * 2.0


def capped(value: float) -> float:
    return min(8.0, value)


def capped_exponential_backoff() -> float:
    return capped(exponential(backoff(jitter())))
