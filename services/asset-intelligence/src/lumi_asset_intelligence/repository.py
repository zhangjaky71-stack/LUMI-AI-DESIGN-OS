from __future__ import annotations

from dataclasses import replace
from threading import RLock
from datetime import datetime
from uuid import UUID

from .model import (
    AccessScope,
    AssetAnalysisRecord,
    AssetIndexVersion,
    SearchFilters,
    UsageSignal,
)


class AssetIntelligenceNotFound(LookupError):
    pass


class InMemoryAssetIndexRepository:
    def __init__(self) -> None:
        self._indexes: dict[tuple[UUID, UUID], AssetIndexVersion] = {}
        self._active: dict[UUID, UUID] = {}
        self._records: dict[tuple[UUID, UUID, UUID], AssetAnalysisRecord] = {}
        self._usage: list[UsageSignal] = []
        self._version_counters: dict[UUID, int] = {}
        self._lock = RLock()

    def reserve_index_version(self, organization_id: UUID) -> int:
        with self._lock:
            value = self._version_counters.get(organization_id, 0) + 1
            self._version_counters[organization_id] = value
            return value

    def create_index(self, value: AssetIndexVersion) -> None:
        key = (value.organization_id, value.id)
        if key in self._indexes:
            raise ValueError("ASSET_INDEX_ALREADY_EXISTS")
        if any(
            item.organization_id == value.organization_id and item.version == value.version
            for item in self._indexes.values()
        ):
            raise ValueError("ASSET_INDEX_VERSION_CONFLICT")
        self._indexes[key] = value

    def get_index(self, organization_id: UUID, index_id: UUID) -> AssetIndexVersion:
        try:
            return self._indexes[(organization_id, index_id)]
        except KeyError as exc:
            raise AssetIntelligenceNotFound(str(index_id)) from exc

    def active_index(self, organization_id: UUID) -> AssetIndexVersion:
        try:
            return self.get_index(organization_id, self._active[organization_id])
        except KeyError as exc:
            raise AssetIntelligenceNotFound("ACTIVE_INDEX_NOT_FOUND") from exc

    def mark_index_ready(
        self, organization_id: UUID, index_id: UUID, coverage_count: int,
    ) -> AssetIndexVersion:
        value = self.get_index(organization_id, index_id)
        if value.state != "BUILDING":
            raise ValueError("ASSET_INDEX_NOT_BUILDING")
        ready = replace(value, state="READY", coverage_count=coverage_count)
        self._indexes[(organization_id, index_id)] = ready
        return ready

    def activate_index(
        self,
        organization_id: UUID,
        index_id: UUID,
        activated_at: datetime,
        expected_active_index_id: UUID | None,
    ) -> AssetIndexVersion:
        candidate = self.get_index(organization_id, index_id)
        if candidate.state != "READY":
            raise ValueError("ASSET_INDEX_NOT_READY")
        previous_id = self._active.get(organization_id)
        if previous_id != expected_active_index_id:
            raise ValueError("ASSET_INDEX_ACTIVE_HEAD_CONFLICT")
        if previous_id is not None:
            previous = self.get_index(organization_id, previous_id)
            self._indexes[(organization_id, previous_id)] = replace(
                previous, state="RETIRED"
            )
        active = replace(candidate, state="ACTIVE", activated_at=activated_at)
        self._indexes[(organization_id, index_id)] = active
        self._active[organization_id] = index_id
        return active

    def upsert_analysis(self, value: AssetAnalysisRecord) -> None:
        self._records[(value.organization_id, value.asset_id, value.index_id)] = value

    def get_analysis(
        self, organization_id: UUID, asset_id: UUID, index_id: UUID,
    ) -> AssetAnalysisRecord | None:
        return self._records.get((organization_id, asset_id, index_id))

    @staticmethod
    def _scope_allows(record: AssetAnalysisRecord, scope: AccessScope) -> bool:
        if record.organization_id != scope.organization_id:
            return False
        if record.state != "READY" or record.deleted_at is not None:
            return False
        if scope.project_ids is not None and record.project_id not in scope.project_ids:
            return False
        if scope.brand_ids is not None and record.brand_id not in scope.brand_ids:
            return False
        if record.rights_level not in scope.allowed_rights:
            return False
        if scope.commercial_use and not record.commercial_use:
            return False
        return set(record.permission_tags).issubset(set(scope.permission_tags))

    @staticmethod
    def _filters_allow(record: AssetAnalysisRecord, filters: SearchFilters) -> bool:
        if filters.media_kinds and record.media_kind not in filters.media_kinds:
            return False
        if filters.project_ids and record.project_id not in filters.project_ids:
            return False
        if filters.brand_ids and record.brand_id not in filters.brand_ids:
            return False
        if filters.rights and record.rights_level not in filters.rights:
            return False
        if filters.tags and not set(filters.tags).issubset(set(record.visual_tags)):
            return False
        if filters.created_after and record.created_at < filters.created_after:
            return False
        if filters.created_before and record.created_at > filters.created_before:
            return False
        return True

    def scoped_candidates(
        self, scope: AccessScope, filters: SearchFilters, index_id: UUID,
    ) -> tuple[AssetAnalysisRecord, ...]:
        # Tenant/access/rights scope is evaluated before any scoring caller sees a record.
        safe = (
            record for record in self._records.values()
            if record.index_id == index_id and self._scope_allows(record, scope)
        )
        filtered = (record for record in safe if self._filters_allow(record, filters))
        return tuple(sorted(filtered, key=lambda item: (str(item.asset_id), item.asset_version)))

    def asset_ids_for_index(self, organization_id: UUID, index_id: UUID) -> set[UUID]:
        return {
            value.asset_id for value in self._records.values()
            if value.organization_id == organization_id and value.index_id == index_id
            and value.state == "READY" and value.deleted_at is None
        }

    def add_usage_signal(self, signal: UsageSignal) -> None:
        self._usage.append(signal)

    def usage_signals(
        self, organization_id: UUID, asset_id: UUID,
    ) -> tuple[UsageSignal, ...]:
        return tuple(
            value for value in self._usage
            if value.organization_id == organization_id and value.asset_id == asset_id
        )

    def mark_deleted(
        self, organization_id: UUID, asset_id: UUID, deleted_at: datetime,
    ) -> None:
        for key, record in tuple(self._records.items()):
            if record.organization_id == organization_id and record.asset_id == asset_id:
                self._records[key] = replace(record, state="DELETING", deleted_at=deleted_at)

    def reconcile_deleted(self, organization_id: UUID, asset_id: UUID) -> int:
        keys = [
            key for key, value in self._records.items()
            if value.organization_id == organization_id and value.asset_id == asset_id
        ]
        for key in keys:
            del self._records[key]
        self._usage = [
            value for value in self._usage
            if not (value.organization_id == organization_id and value.asset_id == asset_id)
        ]
        return len(keys)
