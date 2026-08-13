from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, replace
from datetime import datetime


def hash_token(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_token_hash(secret: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_token(secret), expected_hash)


@dataclass(frozen=True, slots=True)
class IssuedToken:
    plaintext: str
    token_hash: str
    prefix: str


def issue_opaque_token(*, label: str = "lumi", entropy_bytes: int = 32) -> IssuedToken:
    if entropy_bytes < 24:
        raise ValueError("opaque token requires at least 192 bits of entropy")
    secret = secrets.token_urlsafe(entropy_bytes)
    prefix = secrets.token_hex(4)
    plaintext = f"{label}_{prefix}_{secret}"
    return IssuedToken(plaintext=plaintext, token_hash=hash_token(plaintext), prefix=prefix)


@dataclass(frozen=True, slots=True)
class SingleUseTokenRecord:
    token_hash: str
    expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None


def consume_single_use_token(
    record: SingleUseTokenRecord,
    plaintext: str,
    *,
    now: datetime,
) -> SingleUseTokenRecord:
    if record.revoked_at is not None:
        raise PermissionError("TOKEN_REVOKED")
    if record.consumed_at is not None:
        raise PermissionError("TOKEN_ALREADY_USED")
    if now >= record.expires_at:
        raise PermissionError("TOKEN_EXPIRED")
    if not verify_token_hash(plaintext, record.token_hash):
        raise PermissionError("TOKEN_INVALID")
    return replace(record, consumed_at=now)
