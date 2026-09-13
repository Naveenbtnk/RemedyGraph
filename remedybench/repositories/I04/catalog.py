class CircuitBreakerConfig:
    """Unused declaration: this is intentionally not implementation proof."""


OPEN_STATE = True


def safe_fallback() -> dict[str, bool]:
    return {"degraded": True}


def open_catalog_response() -> dict[str, bool]:
    if OPEN_STATE:
        return safe_fallback()
    return {"degraded": False}


def recover_half_open() -> bool:
    return True
