from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .tokens import verify_token_hash


@dataclass(frozen=True, slots=True)
class ApiTokenRecord:
    id: str
    organization_id: str
    name: str
    prefix: str
    secret_hash: str
    scopes: frozenset[str]
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


def validate_api_token(
    record: ApiTokenRecord,
    plaintext: str,
    *,
    required_scope: str,
    now: datetime,
) -> None:
    if record.revoked_at is not None:
        raise PermissionError("API_TOKEN_REVOKED")
    if record.expires_at is not None and now >= record.expires_at:
        raise PermissionError("API_TOKEN_EXPIRED")
    if required_scope not in record.scopes:
        raise PermissionError("API_TOKEN_SCOPE_DENIED")
    if not plaintext.startswith(f"lumi_{record.prefix}_"):
        raise PermissionError("API_TOKEN_INVALID")
    if not verify_token_hash(plaintext, record.secret_hash):
        raise PermissionError("API_TOKEN_INVALID")
