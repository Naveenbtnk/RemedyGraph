"""Stable opaque identifiers for the Day 1 domain records."""

import hashlib


def stable_id(kind: str, *parts: object) -> str:
    """Create a deterministic, opaque identifier within an audit corpus."""

    payload = "\x1f".join([kind, *(str(part) for part in parts)])
    return f"{kind}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"
