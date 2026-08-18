from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SecurityContextError(ValueError):
    code = "SECURITY_CONTEXT_INVALID"


class ContextTrust(StrEnum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    ADMIN_CONFIG = "ADMIN_CONFIG"
    EXTERNAL_UNTRUSTED = "EXTERNAL_UNTRUSTED"
    TOOL_RESULT_UNTRUSTED = "TOOL_RESULT_UNTRUSTED"
    ASSET_EXTRACT_UNTRUSTED = "ASSET_EXTRACT_UNTRUSTED"


_UNTRUSTED = {
    ContextTrust.EXTERNAL_UNTRUSTED,
    ContextTrust.TOOL_RESULT_UNTRUSTED,
    ContextTrust.ASSET_EXTRACT_UNTRUSTED,
}
_FORBIDDEN_METADATA_KEY_MARKERS = (
    "password",
    "passwd",
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "session_secret",
    "cookie",
    "client_secret",
    "private_key",
    "card_number",
    "cvc",
    "cvv",
    "prompt",
    "raw_content",
    "document_text",
    "message_body",
    "artifact_content",
)
_SECRET_VALUE_PREFIXES = (
    "bearer ",
    "sk-",
    "github_pat_",
    "ghp_",
    "gho_",
    "ghu_",
    "ghs_",
    "ghr_",
)


def _normalized_key(value: object) -> str:
    return str(value).strip().casefold().replace("-", "_").replace(".", "_")


def _safe_metadata_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        raise SecurityContextError("SECURITY_CONTEXT_METADATA_DEPTH_EXCEEDED")
    if isinstance(value, Mapping):
        if len(value) > 32:
            raise SecurityContextError("SECURITY_CONTEXT_METADATA_ITEMS_EXCEEDED")
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key).strip()
            if not key or len(key) > 80:
                raise SecurityContextError("SECURITY_CONTEXT_METADATA_KEY_INVALID")
            normalized = _normalized_key(key)
            if any(marker in normalized for marker in _FORBIDDEN_METADATA_KEY_MARKERS):
                raise SecurityContextError("SECURITY_CONTEXT_METADATA_SENSITIVE_KEY_FORBIDDEN")
            result[key] = _safe_metadata_value(item, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > 32:
            raise SecurityContextError("SECURITY_CONTEXT_METADATA_ITEMS_EXCEEDED")
        return [_safe_metadata_value(item, depth=depth + 1) for item in value]
    if isinstance(value, bytes | bytearray):
        raise SecurityContextError("SECURITY_CONTEXT_METADATA_BINARY_FORBIDDEN")
    if isinstance(value, str):
        if len(value) > 512:
            raise SecurityContextError("SECURITY_CONTEXT_METADATA_VALUE_TOO_LONG")
        normalized = value.strip().casefold()
        if normalized.startswith(_SECRET_VALUE_PREFIXES) or any(
            marker in normalized
            for marker in (
                "x-amz-signature=",
                "access_token=",
                "refresh_token=",
                "api_key=",
                "apikey=",
            )
        ):
            raise SecurityContextError("SECURITY_CONTEXT_METADATA_SECRET_VALUE_FORBIDDEN")
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise SecurityContextError("SECURITY_CONTEXT_METADATA_TYPE_FORBIDDEN")


class ContextEnvelope(BaseModel):
    """Security label carried with model context.

    This object intentionally separates *data trust* from authorization. External
    content can be useful context, but it can never grant permissions, change the
    caller principal, or mark itself authoritative.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trust: ContextTrust
    source_type: str = Field(min_length=1, max_length=80)
    source_ref: str = Field(min_length=1, max_length=512)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authoritative: bool = False
    can_authorize: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_ref")
    @classmethod
    def sanitize_source_ref(cls, value: str) -> str:
        value = value.strip()
        normalized = value.casefold()
        if any(
            marker in normalized
            for marker in (
                "access_token=",
                "refresh_token=",
                "api_key=",
                "apikey=",
                "x-amz-signature=",
                "sig=",
            )
        ):
            raise SecurityContextError("SECURITY_CONTEXT_SECRET_REF_FORBIDDEN")
        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise SecurityContextError("SECURITY_CONTEXT_SOURCE_REF_INVALID") from exc
        if parsed.scheme in {"http", "https"}:
            if not parsed.hostname or parsed.username or parsed.password:
                raise SecurityContextError("SECURITY_CONTEXT_SOURCE_REF_INVALID")
            # Query and fragment often carry tracking identifiers or transient access
            # material. Context identity keeps only the stable public URL portion.
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        return value

    @field_validator("metadata")
    @classmethod
    def validate_safe_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        safe = _safe_metadata_value(value)
        if not isinstance(safe, dict):  # pragma: no cover - root type is fixed by Pydantic
            raise SecurityContextError("SECURITY_CONTEXT_METADATA_INVALID")
        return safe

    @model_validator(mode="after")
    def enforce_trust_boundary(self) -> ContextEnvelope:
        if self.trust in _UNTRUSTED and (self.authoritative or self.can_authorize):
            raise SecurityContextError("SECURITY_UNTRUSTED_CONTEXT_CANNOT_AUTHORIZE")
        if self.can_authorize and self.trust not in {
            ContextTrust.SYSTEM,
            ContextTrust.ADMIN_CONFIG,
        }:
            raise SecurityContextError("SECURITY_AUTHORIZATION_CONTEXT_NOT_TRUSTED")
        return self

    @classmethod
    def from_text(
        cls,
        *,
        trust: ContextTrust,
        source_type: str,
        source_ref: str,
        text: str,
        authoritative: bool = False,
        can_authorize: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ContextEnvelope:
        return cls(
            trust=trust,
            source_type=source_type,
            source_ref=source_ref,
            content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            authoritative=authoritative,
            can_authorize=can_authorize,
            metadata=dict(metadata or {}),
        )

    @property
    def is_untrusted(self) -> bool:
        return self.trust in _UNTRUSTED
