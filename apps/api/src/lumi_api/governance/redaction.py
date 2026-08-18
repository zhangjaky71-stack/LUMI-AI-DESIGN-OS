from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_REDACTED = "[REDACTED]"
_FORBIDDEN_KEY_PARTS = (
    "password",
    "passwd",
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "session_secret",
    "cookie",
    "card_number",
    "pan",
    "cvc",
    "cvv",
    "client_secret",
    "private_key",
)
_CONTENT_KEY_PARTS = (
    "prompt",
    "raw_content",
    "document_text",
    "artifact_content",
    "message_body",
)
_URL_KEY_PARTS = ("url", "uri", "href")
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
)


def sha256_ref(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return _REDACTED
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    if parsed.query or parsed.fragment:
        return _REDACTED
    return value


def redact_audit_text(value: str) -> str:
    normalized = value.strip()
    if normalized.casefold().startswith("bearer "):
        return _REDACTED
    if any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
        return _REDACTED
    return value


def _normalized_key(key: object) -> str:
    return str(key).strip().casefold().replace("-", "_")


def _matches(key: str, patterns: tuple[str, ...]) -> bool:
    return any(part in key for part in patterns)


def redact_audit_value(value: Any, *, key_hint: str = "") -> Any:
    key = _normalized_key(key_hint)
    if _matches(key, _FORBIDDEN_KEY_PARTS):
        return _REDACTED

    if isinstance(value, Mapping):
        return {
            str(item_key): redact_audit_value(item_value, key_hint=str(item_key))
            for item_key, item_value in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_audit_value(item, key_hint=key_hint) for item in value]

    if isinstance(value, bytes):
        return f"sha256:{hashlib.sha256(value).hexdigest()}"

    if isinstance(value, str):
        if _matches(key, _CONTENT_KEY_PARTS):
            return sha256_ref(value)
        if _matches(key, _URL_KEY_PARTS):
            return sanitize_url(value)
        return redact_audit_text(value)

    if value is None or isinstance(value, (bool, int, float)):
        return value

    return str(value)


def redact_audit_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): redact_audit_value(item, key_hint=str(key))
        for key, item in value.items()
    }
