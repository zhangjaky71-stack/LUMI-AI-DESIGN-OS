from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlparse


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def issue_secret(bytes_of_entropy: int = 32) -> str:
    if bytes_of_entropy < 24:
        raise ValueError("security token entropy must be at least 192 bits")
    return secrets.token_urlsafe(bytes_of_entropy)


def verify_hashed_secret(secret: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(secret), expected_hash)


def validate_csrf(
    *,
    method: str,
    origin: str | None,
    allowed_origins: frozenset[str],
    csrf_cookie: str | None,
    csrf_header: str | None,
) -> None:
    if method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    if origin is None:
        raise ValueError("CSRF_ORIGIN_REQUIRED")
    parsed = urlparse(origin)
    normalized_origin = f"{parsed.scheme}://{parsed.netloc}"
    if normalized_origin not in allowed_origins:
        raise ValueError("CSRF_ORIGIN_DENIED")
    if not csrf_cookie or not csrf_header:
        raise ValueError("CSRF_TOKEN_REQUIRED")
    if not hmac.compare_digest(csrf_cookie, csrf_header):
        raise ValueError("CSRF_TOKEN_MISMATCH")


@dataclass(slots=True)
class _RateBucket:
    started_at: datetime
    count: int


@dataclass(slots=True)
class MemoryRateLimiter:
    buckets: dict[tuple[str, str], _RateBucket] = field(default_factory=dict)

    def hit(
        self,
        *,
        action: str,
        subject_key: str,
        now: datetime,
        limit: int,
        window: timedelta,
    ) -> None:
        if limit < 1 or window <= timedelta(0):
            raise ValueError("invalid rate limit policy")
        key = (action, subject_key)
        bucket = self.buckets.get(key)
        if bucket is None or now - bucket.started_at >= window:
            self.buckets[key] = _RateBucket(started_at=now, count=1)
            return
        if bucket.count >= limit:
            raise ValueError("RATE_LIMITED")
        bucket.count += 1
