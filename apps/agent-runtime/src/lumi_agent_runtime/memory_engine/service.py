from __future__ import annotations

from datetime import datetime
from uuid import UUID

from .contracts import (
    MemoryAccessContext,
    MemoryCandidate,
    MemoryDecision,
    MemoryRecord,
    MemorySearchQuery,
    MemorySearchResult,
)
from .governance import MemoryGovernanceService
from .pipeline import MemoryCandidatePipeline
from .postgres_repository import PostgresMemoryRepository
from .repository import MemoryRepository
from .retrieval import MemoryRetriever


class MemoryEngineService:
    """Reference service for a repository already scoped to one transaction/lifetime."""

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    async def remember(self, candidate: MemoryCandidate, *, access: MemoryAccessContext, now: datetime | None = None) -> MemoryDecision:
        return await MemoryCandidatePipeline(self.repository).process(candidate, access=access, now=now)

    async def search(self, query: MemorySearchQuery) -> tuple[MemorySearchResult, ...]:
        return await MemoryRetriever(self.repository).search(query)

    async def delete(self, memory_id: UUID, *, access: MemoryAccessContext, now: datetime | None = None) -> MemoryRecord:
        return await MemoryGovernanceService(self.repository).delete(memory_id, access=access, now=now)

    async def consolidate(self, *, organization_id: UUID, now: datetime | None = None) -> tuple[UUID, ...]:
        return await MemoryGovernanceService(self.repository).consolidate(organization_id=organization_id, now=now)


class TransactionalMemoryEngineService:
    """Production service: every operation is enclosed by the repository transaction boundary."""

    def __init__(self, repository: PostgresMemoryRepository) -> None:
        self.repository = repository

    async def remember(self, candidate: MemoryCandidate, *, access: MemoryAccessContext, now: datetime | None = None) -> MemoryDecision:
        async with self.repository.transaction() as session:
            return await MemoryCandidatePipeline(session).process(candidate, access=access, now=now)

    async def search(self, query: MemorySearchQuery) -> tuple[MemorySearchResult, ...]:
        async with self.repository.transaction() as session:
            return await MemoryRetriever(session).search(query)

    async def delete(self, memory_id: UUID, *, access: MemoryAccessContext, now: datetime | None = None) -> MemoryRecord:
        async with self.repository.transaction() as session:
            return await MemoryGovernanceService(session).delete(memory_id, access=access, now=now)

    async def consolidate(self, *, organization_id: UUID, now: datetime | None = None) -> tuple[UUID, ...]:
        async with self.repository.transaction() as session:
            return await MemoryGovernanceService(session).consolidate(organization_id=organization_id, now=now)
