from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Protocol
from uuid import UUID

from .contracts import PresenceState


PRESENCE_TTL_SECONDS = 30
PRESENCE_HEARTBEAT_SECONDS = 10


class PresencePort(Protocol):
    def heartbeat(self, value: PresenceState, *, ttl_seconds: int = PRESENCE_TTL_SECONDS) -> PresenceState: ...
    def list_project(self, project_id: UUID, *, now: datetime | None = None) -> tuple[PresenceState, ...]: ...
    def remove(self, project_id: UUID, user_id: str) -> None: ...


class InMemoryPresencePort:
    """Test/dev TTL adapter. Production NODE-61 requires a Redis-backed adapter."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._values: dict[tuple[UUID, str], tuple[PresenceState, datetime]] = {}

    def heartbeat(
        self, value: PresenceState, *, ttl_seconds: int = PRESENCE_TTL_SECONDS
    ) -> PresenceState:
        if ttl_seconds < 1 or ttl_seconds > 300:
            raise ValueError("PRESENCE_TTL_OUT_OF_RANGE")
        now = datetime.now(UTC)
        normalized = value.model_copy(update={"last_seen_at": now})
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._lock:
            self._values[(value.project_id, value.user_id)] = (normalized, expires_at)
        return normalized

    def list_project(
        self, project_id: UUID, *, now: datetime | None = None
    ) -> tuple[PresenceState, ...]:
        current = now or datetime.now(UTC)
        with self._lock:
            expired = [key for key, (_, expiry) in self._values.items() if expiry <= current]
            for key in expired:
                self._values.pop(key, None)
            values = [
                state
                for (candidate_project_id, _), (state, expiry) in self._values.items()
                if candidate_project_id == project_id and expiry > current
            ]
        return tuple(sorted(values, key=lambda item: (item.display_name.lower(), item.user_id)))

    def remove(self, project_id: UUID, user_id: str) -> None:
        with self._lock:
            self._values.pop((project_id, user_id), None)
