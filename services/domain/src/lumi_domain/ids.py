from __future__ import annotations

import secrets
import time
from uuid import UUID

type DomainId = UUID


def new_uuid7(*, unix_ms: int | None = None) -> DomainId:
    """Create an RFC 9562 UUIDv7 without persistence or third-party dependencies."""
    timestamp_ms = int(time.time_ns() // 1_000_000 if unix_ms is None else unix_ms)
    if not 0 <= timestamp_ms < 1 << 48:
        raise ValueError("UUIDv7 timestamp must fit in 48 bits")

    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return UUID(int=value)


def uuid7_timestamp_ms(value: DomainId) -> int:
    if value.version != 7:
        raise ValueError("expected UUIDv7")
    return value.int >> 80
