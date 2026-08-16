from __future__ import annotations

import secrets
import time
from uuid import UUID


def new_uuid7(*, unix_ms: int | None = None) -> UUID:
    timestamp = int(time.time() * 1000) if unix_ms is None else unix_ms
    if not 0 <= timestamp < 1 << 48:
        raise ValueError("unix_ms must fit in 48 bits")
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = timestamp << 80
    value |= 0x7 << 76
    value |= random_a << 64
    value |= 0b10 << 62
    value |= random_b
    return UUID(int=value)
