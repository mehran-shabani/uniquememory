from __future__ import annotations

from security.dlp import DLPSanitizer, sanitize_output, sanitize_text


def test_sanitize_text_replaces_sensitive_tokens():
    sanitized = sanitize_text("Contact me at alice@example.com or 4111-1111-1111-1111")
    assert "[REDACTED-EMAIL]" in sanitized
    assert "[REDACTED-PAN]" in sanitized


def test_sanitize_output_handles_nested_structures():
    payload = {
        "message": "SSN 123-45-6789",
        "details": [{"token": "abc"}, "555-123-4567"],
        "profile": {"Email": "bob@example.com"},
    }
    sanitized = sanitize_output(payload)
    assert sanitized["message"] == "SSN [REDACTED-SSN]"
    assert sanitized["details"][0]["token"] == "[REMOVED]"
    assert sanitized["details"][1] == "[REDACTED-PHONE]"
    assert sanitized["profile"]["Email"] == "[REDACTED-EMAIL]"


def test_custom_sanitizer_allows_overrides():
    sanitizer = DLPSanitizer(patterns=[], key_blocklist=["api_key"], key_substrings=[])
    sanitized = sanitizer.sanitize({"api_key": "secret", "note": "ok"})
    assert sanitized["api_key"] == "[REMOVED]"
    assert sanitized["note"] == "ok"
