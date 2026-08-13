from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


class RateLimitExceeded(PermissionError):
    pass


class RateLimiter(Protocol):
    def consume(self, key: str, *, now: datetime, limit: int, window: timedelta) -> None: ...


@dataclass(slots=True)
class InMemorySlidingWindowRateLimiter:
    """Reference/dev limiter. Production multi-instance deployments must use shared storage."""

    _events: dict[str, deque[datetime]]

    def __init__(self) -> None:
        self._events = defaultdict(deque)

    def consume(self, key: str, *, now: datetime, limit: int, window: timedelta) -> None:
        if limit <= 0 or window.total_seconds() <= 0:
            raise ValueError("rate limit/window must be positive")
        events = self._events[key]
        cutoff = now - window
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            raise RateLimitExceeded("RATE_LIMITED")
        events.append(now)
