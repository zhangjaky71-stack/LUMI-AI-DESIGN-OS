from __future__ import annotations

from typing import Protocol

from .models import SandboxAuditEvent


class AuditSink(Protocol):
    async def emit(self, event: SandboxAuditEvent) -> None: ...


class MemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[SandboxAuditEvent] = []

    async def emit(self, event: SandboxAuditEvent) -> None:
        self.events.append(event)
