import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = {
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "apikey",
    "token",
}
_SENSITIVE_COMPOUND_KEYS = {
    "access_token",
    "api_key",
    "client_secret",
    "proxy_authorization",
    "refresh_token",
    "set_cookie",
}
_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


class AttributeRedactor:
    def redact(self, value: Any, *, key: str | None = None) -> Any:
        if key is not None and self._is_sensitive_key(key):
            return REDACTED
        if isinstance(value, Mapping):
            return {
                item_key: self.redact(item, key=str(item_key))
                for item_key, item in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            redacted = value
            for pattern in _VALUE_PATTERNS:
                redacted = pattern.sub(REDACTED, redacted)
            return redacted
        return value

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
        if normalized in _SENSITIVE_COMPOUND_KEYS or normalized in _SENSITIVE_KEY_PARTS:
            return True
        parts = set(normalized.split("_"))
        return bool(parts & (_SENSITIVE_KEY_PARTS - {"token"})) or normalized.endswith("_token")

