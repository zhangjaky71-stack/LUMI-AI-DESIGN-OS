from __future__ import annotations

import hmac
from dataclasses import dataclass, replace
from datetime import datetime
from urllib.parse import urlsplit

from .tokens import hash_token


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_token_hash: str
    csrf_token_hash: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    organization_id: str | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    user_agent_hash: str | None = None


def validate_session(record: SessionRecord, *, now: datetime) -> None:
    if record.revoked_at is not None:
        raise PermissionError("SESSION_REVOKED")
    if now >= record.expires_at:
        raise PermissionError("SESSION_EXPIRED")


def touch_session(record: SessionRecord, *, now: datetime) -> SessionRecord:
    validate_session(record, now=now)
    return replace(record, last_seen_at=now)


def revoke_session(record: SessionRecord, *, now: datetime) -> SessionRecord:
    if record.revoked_at is not None:
        return record
    return replace(record, revoked_at=now)


def validate_csrf(
    record: SessionRecord,
    *,
    csrf_token: str | None,
    origin: str | None,
    allowed_origins: frozenset[str],
) -> None:
    if csrf_token is None or origin is None:
        raise PermissionError("CSRF_REQUIRED")
    parsed = urlsplit(origin)
    normalized_origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    if normalized_origin not in allowed_origins:
        raise PermissionError("CSRF_ORIGIN_DENIED")
    if not hmac.compare_digest(hash_token(csrf_token), record.csrf_token_hash):
        raise PermissionError("CSRF_TOKEN_INVALID")


@dataclass(frozen=True, slots=True)
class CookieContract:
    name: str = "lumi_session"
    http_only: bool = True
    secure: bool = True
    same_site: str = "lax"
    path: str = "/"

    def __post_init__(self) -> None:
        if not self.http_only:
            raise ValueError("session cookie must be HttpOnly")
        if self.same_site not in {"lax", "strict"}:
            raise ValueError("session SameSite must be lax or strict in V1")
        if self.path != "/":
            raise ValueError("session cookie Path must be /")
