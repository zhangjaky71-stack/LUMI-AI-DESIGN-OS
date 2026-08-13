from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .contracts import MCPDiscoveryResult


class MCPClock(Protocol):
    def monotonic(self) -> float: ...


class SystemMCPClock:
    def monotonic(self) -> float:
        return time.monotonic()


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    result: MCPDiscoveryResult
    expires_at: float


class MCPDiscoveryCache:
    """Caches discovery/tool metadata only; execution results are never cached here."""

    def __init__(self, *, clock: MCPClock | None = None) -> None:
        self.clock = clock or SystemMCPClock()
        self._entries: dict[tuple[str, str], _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(
        self,
        server_id: str,
        *,
        organization_id: UUID,
    ) -> MCPDiscoveryResult | None:
        key = (server_id, str(organization_id))
        now = self.clock.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if now >= entry.expires_at:
                self._entries.pop(key, None)
                return None
            return entry.result

    def put(
        self,
        server_id: str,
        *,
        organization_id: UUID,
        result: MCPDiscoveryResult,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            return
        ttl = min(ttl_seconds, 86_400)
        key = (server_id, str(organization_id))
        with self._lock:
            self._entries[key] = _CacheEntry(
                result=result,
                expires_at=self.clock.monotonic() + ttl,
            )

    def invalidate(self, server_id: str, *, organization_id: UUID) -> None:
        with self._lock:
            self._entries.pop((server_id, str(organization_id)), None)
