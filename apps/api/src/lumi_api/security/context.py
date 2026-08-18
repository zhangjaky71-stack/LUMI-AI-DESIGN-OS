from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

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
    def reject_secret_bearing_refs(cls, value: str) -> str:
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
        return value

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
