from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import Field, field_validator

from lumi_api.domain.ids import new_uuid7

from .models import ArtifactContractModel


class StoredObject(ArtifactContractModel):
    organization_id: UUID
    bucket: str = Field(min_length=1, max_length=128)
    storage_key: str = Field(min_length=1, max_length=2_000)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def location(self) -> tuple[str, str]:
        return (self.bucket, self.storage_key)


class GcCandidate(ArtifactContractModel):
    id: UUID
    organization_id: UUID
    bucket: str
    storage_key: str
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    marked_at: datetime
    not_before: datetime

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("gc candidate id must be UUIDv7")
        return value

    @field_validator("marked_at", "not_before")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("GC timestamps must be timezone-aware")
        return value

    @property
    def location(self) -> tuple[str, str]:
        return (self.bucket, self.storage_key)


def mark_gc_candidates(
    objects: tuple[StoredObject, ...],
    *,
    live_references: frozenset[tuple[str, str]],
    retention_references: frozenset[tuple[str, str]],
    legal_hold_references: frozenset[tuple[str, str]],
    marked_at: datetime,
    delay: timedelta,
) -> tuple[GcCandidate, ...]:
    if marked_at.tzinfo is None or marked_at.utcoffset() is None:
        raise ValueError("marked_at must be timezone-aware")
    if delay <= timedelta(0):
        raise ValueError("GC delay must be positive")
    protected = live_references | retention_references | legal_hold_references
    candidates = [
        GcCandidate(
            id=new_uuid7(),
            organization_id=item.organization_id,
            bucket=item.bucket,
            storage_key=item.storage_key,
            checksum_sha256=item.checksum_sha256,
            marked_at=marked_at,
            not_before=marked_at + delay,
        )
        for item in objects
        if item.location not in protected
    ]
    return tuple(sorted(candidates, key=lambda item: (item.bucket, item.storage_key)))


def confirm_gc_deletions(
    candidates: tuple[GcCandidate, ...],
    *,
    live_references: frozenset[tuple[str, str]],
    retention_references: frozenset[tuple[str, str]],
    legal_hold_references: frozenset[tuple[str, str]],
    checked_at: datetime,
) -> tuple[GcCandidate, ...]:
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ValueError("checked_at must be timezone-aware")
    protected = live_references | retention_references | legal_hold_references
    safe = [
        item
        for item in candidates
        if checked_at >= item.not_before and item.location not in protected
    ]
    return tuple(sorted(safe, key=lambda item: (item.bucket, item.storage_key)))
