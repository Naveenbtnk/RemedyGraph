"""Secret-like value redaction used before evidence is stored or displayed."""

import re
from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import JsonValue

REDACTED = "[REDACTED]"

_SECRET_KEY = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?key|secret|token|password|passwd|private[_-]?key|credential)"
)
_ASSIGNMENT = re.compile(
    r"(?im)(\b(?:api[_-]?key|access[_-]?key|secret|token|password|passwd|"
    r"private[_-]?key|credential)s?\b\s*[:=]\s*)([\"'][^\"']*[\"']|[^\s,;#]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
_AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


def redact_text(text: str) -> str:
    """Redact common credentials while preserving line counts and surrounding context."""

    redacted = _PRIVATE_KEY.sub(lambda match: REDACTED + ("\n" * match.group(0).count("\n")), text)
    redacted = _BEARER.sub(f"Bearer {REDACTED}", redacted)
    redacted = _AWS_KEY.sub(REDACTED, redacted)
    return _ASSIGNMENT.sub(lambda match: f"{match.group(1)}{REDACTED}", redacted)


def is_secret_key(key: object) -> bool:
    return isinstance(key, str) and _SECRET_KEY.search(key) is not None


def redact_json(value: object, key: object | None = None) -> JsonValue:
    """Recursively redact secret-like configuration values into JSON-compatible data."""

    if is_secret_key(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_json(item_value, item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_json(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return cast(JsonValue, value)
    return str(value)
