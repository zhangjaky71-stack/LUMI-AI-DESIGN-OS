from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import UUID

from .contracts import MemoryCandidate, MemoryRecord, MemoryStatus
from .errors import MemoryConflictError


class MemoryRepository(Protocol):
    async def get(self, memory_id: UUID) -> MemoryRecord | None: ...
    async def find_active_by_key(self, *, organization_id: UUID, scope_type: str, scope_id: str, kind: str, semantic_key: str) -> tuple[MemoryRecord, ...]: ...
    async def list_active(self, *, organization_id: UUID) -> tuple[MemoryRecord, ...]: ...
    async def list_records(self, *, organization_id: UUID) -> tuple[MemoryRecord, ...]: ...
    async def insert_record(self, record: MemoryRecord) -> MemoryRecord: ...
    async def update_record(self, record: MemoryRecord, *, expected_version: int) -> MemoryRecord: ...
    async def insert_candidate(self, candidate: MemoryCandidate, *, outcome: str, reason: str | None) -> None: ...
    async def soft_delete(self, memory_id: UUID, *, deleted_at: datetime, expected_version: int) -> MemoryRecord: ...


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._records: dict[UUID, MemoryRecord] = {}
        self._candidates: dict[UUID, tuple[MemoryCandidate, str, str | None]] = {}

    async def get(self, memory_id: UUID) -> MemoryRecord | None:
        with self._lock:
            return self._records.get(memory_id)

    async def find_active_by_key(self, *, organization_id: UUID, scope_type: str, scope_id: str, kind: str, semantic_key: str) -> tuple[MemoryRecord, ...]:
        now = datetime.now(UTC)
        with self._lock:
            return tuple(item for item in self._records.values() if item.organization_id == organization_id and item.scope_type.value == scope_type and item.scope_id == scope_id and item.kind.value == kind and item.semantic_key == semantic_key and item.status == MemoryStatus.ACTIVE and item.deleted_at is None and (item.expires_at is None or item.expires_at > now))

    async def list_active(self, *, organization_id: UUID) -> tuple[MemoryRecord, ...]:
        now = datetime.now(UTC)
        with self._lock:
            return tuple(item for item in self._records.values() if item.organization_id == organization_id and item.status == MemoryStatus.ACTIVE and item.deleted_at is None and (item.expires_at is None or item.expires_at > now))

    async def list_records(self, *, organization_id: UUID) -> tuple[MemoryRecord, ...]:
        with self._lock:
            return tuple(item for item in self._records.values() if item.organization_id == organization_id)

    async def insert_record(self, record: MemoryRecord) -> MemoryRecord:
        with self._lock:
            if record.memory_id in self._records:
                raise MemoryConflictError("MEMORY_RECORD_DUPLICATE")
            self._records[record.memory_id] = record
            return record

    async def update_record(self, record: MemoryRecord, *, expected_version: int) -> MemoryRecord:
        with self._lock:
            current = self._records.get(record.memory_id)
            if current is None or current.version != expected_version:
                raise MemoryConflictError("MEMORY_VERSION_CONFLICT")
            if record.version != expected_version + 1:
                raise MemoryConflictError("MEMORY_VERSION_NOT_INCREMENTED")
            self._records[record.memory_id] = record
            return record

    async def insert_candidate(self, candidate: MemoryCandidate, *, outcome: str, reason: str | None) -> None:
        with self._lock:
            self._candidates[candidate.candidate_id] = (candidate, outcome, reason)

    async def soft_delete(self, memory_id: UUID, *, deleted_at: datetime, expected_version: int) -> MemoryRecord:
        with self._lock:
            current = self._records[memory_id]
            if current.version != expected_version:
                raise MemoryConflictError("MEMORY_VERSION_CONFLICT")
            updated = replace(current, status=MemoryStatus.DELETED, deleted_at=deleted_at, version=current.version + 1)
            self._records[memory_id] = updated
            return updated

    def candidates(self) -> tuple[tuple[MemoryCandidate, str, str | None], ...]:
        with self._lock:
            return tuple(self._candidates.values())
