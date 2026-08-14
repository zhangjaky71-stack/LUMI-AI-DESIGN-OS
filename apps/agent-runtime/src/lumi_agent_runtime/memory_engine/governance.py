from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from .contracts import MemoryAccessContext, MemoryKind, MemoryRecord, MemoryStatus
from .errors import MemoryRetentionError, MemoryScopeError
from .policy import can_delete_scope
from .repository import MemoryRepository


class MemoryGovernanceService:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    async def delete(self, memory_id: UUID, *, access: MemoryAccessContext, now: datetime | None = None) -> MemoryRecord:
        record = await self.repository.get(memory_id)
        if record is None or record.organization_id != access.organization_id:
            raise MemoryScopeError("MEMORY_DELETE_NOT_FOUND_OR_DENIED")
        if record.retention_hold:
            raise MemoryRetentionError("MEMORY_RETENTION_HOLD")
        if not can_delete_scope(record.scope_type, record.scope_id, access):
            raise MemoryScopeError("MEMORY_DELETE_SCOPE_DENIED")
        return await self.repository.soft_delete(
            memory_id,
            deleted_at=now or datetime.now(UTC),
            expected_version=record.version,
        )

    async def consolidate(self, *, organization_id: UUID, now: datetime | None = None) -> tuple[UUID, ...]:
        observed_at = now or datetime.now(UTC)
        records = await self.repository.list_records(organization_id=organization_id)
        changed: list[UUID] = []
        for record in records:
            if (
                record.status == MemoryStatus.ACTIVE
                and record.expires_at is not None
                and record.expires_at <= observed_at
                and not record.retention_hold
            ):
                expired = replace(
                    record,
                    status=MemoryStatus.EXPIRED,
                    valid_to=observed_at,
                    version=record.version + 1,
                )
                await self.repository.update_record(expired, expected_version=record.version)
                changed.append(record.memory_id)

        active = [
            item
            for item in await self.repository.list_active(organization_id=organization_id)
            if item.kind == MemoryKind.EPISODIC_SUMMARY
        ]
        groups: dict[tuple[str, str, str], list[MemoryRecord]] = {}
        for item in active:
            groups.setdefault((item.scope_type.value, item.scope_id, item.semantic_key), []).append(item)
        for group in groups.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda item: (item.confidence, item.version, item.created_at), reverse=True)
            survivor = group[0]
            refs = list(survivor.source_refs)
            seen = {(x.source_type, x.source_id, x.version, x.content_hash) for x in refs}
            for duplicate in group[1:]:
                for ref in duplicate.source_refs:
                    key = (ref.source_type, ref.source_id, ref.version, ref.content_hash)
                    if key not in seen:
                        seen.add(key)
                        refs.append(ref)
                superseded = replace(
                    duplicate,
                    status=MemoryStatus.SUPERSEDED,
                    valid_to=observed_at,
                    version=duplicate.version + 1,
                    metadata={**duplicate.metadata, "consolidated_into": str(survivor.memory_id)},
                )
                await self.repository.update_record(superseded, expected_version=duplicate.version)
                changed.append(duplicate.memory_id)
            updated = replace(
                survivor,
                source_refs=tuple(refs),
                version=survivor.version + 1,
                metadata={**survivor.metadata, "consolidated": True},
            )
            await self.repository.update_record(updated, expected_version=survivor.version)
            changed.append(survivor.memory_id)
        return tuple(changed)
