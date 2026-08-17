from __future__ import annotations

import secrets
import time
from uuid import UUID


def new_uuid7(*, unix_ms: int | None = None) -> UUID:
    timestamp = int(time.time() * 1000) if unix_ms is None else unix_ms
    value = timestamp << 80
    value |= 0x7 << 76
    value |= secrets.randbits(12) << 64
    value |= 0b10 << 62
    value |= secrets.randbits(62)
    return UUID(int=value)
