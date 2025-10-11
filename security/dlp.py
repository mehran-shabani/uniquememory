"""Data loss prevention utilities for sanitizing outbound payloads."""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


_DEFAULT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Social security numbers (US-style)
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED-SSN]"),
    # Credit card numbers (13–19 contiguous digits)
    (re.compile(r"\b\d{13,19}\b"), "[REDACTED-PAN]"),
    # Credit card numbers with optional single separators
    (re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"), "[REDACTED-PAN]"),
    # Email addresses
    (re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE), "[REDACTED-EMAIL]"),
    # Phone numbers with separators
    (re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[REDACTED-PHONE]"),
)

_KEY_BLOCKLIST: tuple[str, ...] = (
    "ssn",
    "social_security",
    "social_security_number",
    "credit_card",
    "card_number",
    "pan",
    "password",
    "passphrase",
    "secret",
    "token",
    "api_key",
)

_KEY_SUBSTRINGS: tuple[str, ...] = (
    "secret",
    "token",
    "password",
)

_REDACTED_VALUE = "[REMOVED]"


class DLPSanitizer:
    """Apply pattern-based redaction and key removal rules to output payloads."""

    def __init__(
        self,
        patterns: Iterable[tuple[re.Pattern[str], str]] | None = None,
        key_blocklist: Iterable[str] | None = None,
        key_substrings: Iterable[str] | None = None,
    ) -> None:
        self.patterns = tuple(patterns) if patterns is not None else _DEFAULT_PATTERNS
        self.key_blocklist = {k.lower() for k in (key_blocklist or _KEY_BLOCKLIST)}
        self.key_substrings = tuple(s.lower() for s in (key_substrings or _KEY_SUBSTRINGS))

    def sanitize(self, payload: Any) -> Any:
        """Return a sanitized copy of *payload* suitable for outbound use."""
        return self._sanitize_value(payload)

    def sanitize_text(self, text: str) -> str:
        """Redact sensitive tokens from a text value."""
        sanitized = text
        for pattern, replacement in self.patterns:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    def _should_redact_key(self, key: str) -> bool:
        lower = key.lower()
        if lower in self.key_blocklist:
            return True
        return any(substr in lower for substr in self.key_substrings)

    def _sanitize_mapping(self, payload: Mapping[str, Any] | MutableMapping[str, Any]) -> Mapping[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(key, str) and self._should_redact_key(key):
                sanitized[key] = _REDACTED_VALUE
            else:
                sanitized[key] = self._sanitize_value(value)
        return sanitized

    def _sanitize_sequence(self, payload: Sequence[Any]) -> Sequence[Any]:
        sanitized_items = [self._sanitize_value(item) for item in payload]
        if isinstance(payload, tuple):
            return tuple(sanitized_items)
        return sanitized_items

    def _sanitize_value(self, payload: Any) -> Any:
        if isinstance(payload, str):
            return self.sanitize_text(payload)
        if isinstance(payload, Mapping):
            return self._sanitize_mapping(payload)
        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
            return self._sanitize_sequence(payload)
        return payload


_sanitizer = DLPSanitizer()


def sanitize_output(payload: Any) -> Any:
    """Sanitize *payload* using the default DLP sanitizer."""
    return _sanitizer.sanitize(payload)


def sanitize_text(text: str) -> str:
    """Sanitize a text fragment using the default DLP sanitizer."""
    return _sanitizer.sanitize_text(text)


__all__ = ["DLPSanitizer", "sanitize_output", "sanitize_text"]
