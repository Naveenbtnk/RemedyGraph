MAX_RETRY_ATTEMPTS = 3


def charge_with_retry(operation):
    """Bound payment provider retries to three total attempts."""
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            return operation()
        except TimeoutError:
            if attempt == MAX_RETRY_ATTEMPTS - 1:
                raise
