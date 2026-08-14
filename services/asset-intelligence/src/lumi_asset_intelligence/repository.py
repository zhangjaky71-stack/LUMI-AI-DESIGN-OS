from __future__ import annotations

from dataclasses import replace

from .model import (
    AccessScope,
    AssetAnalysisRecord,
    AssetIndexRepository,
    AssetSearchFilters,
    UsageSignal,
)


class InMemoryAssetIndexRepository(AssetIndexRepository):
    """Conformance repository whose retrieval primitive is scope-first by construction."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], AssetAnalysisRecord] = {}
        self._usage: list[UsageSignal] = []

    def upsert_analysis(self, record: AssetAnalysisRecord) -> None:
        key = (record.organization_id, record.asset_id, record.index_id)
        self._records[key] = record

    def get_analysis(
        self,
        organization_id: str,
        asset_id: str,
        index_id: str,
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
        if record.rights not in scope.allowed_rights:
            return False
        if scope.commercial_use and not record.commercial_use_allowed:
            return False
        required = set(record.permission_tags)
        if required and not required.issubset(set(scope.permission_tags)):
            return False
        return True

    @staticmethod
    def _filters_allow(record: AssetAnalysisRecord, filters: AssetSearchFilters) -> bool:
        if filters.media_types and record.media_type not in filters.media_types:
            return False
        if filters.project_ids and record.project_id not in filters.project_ids:
            return False
        if filters.brand_ids and record.brand_id not in filters.brand_ids:
            return False
        if filters.rights and record.rights not in filters.rights:
            return False
        if filters.tags and not set(filters.tags).issubset(set(record.visual_tags)):
            return False
        if filters.created_after and record.created_at < filters.created_after:
            return False
        if filters.created_before and record.created_at > filters.created_before:
            return False
        return True

    def scoped_candidates(
        self,
        scope: AccessScope,
        filters: AssetSearchFilters,
        index_id: str,
    ) -> tuple[AssetAnalysisRecord, ...]:
        # Security boundary: tenant/access/rights is evaluated before any text/vector scoring.
        safe = (
            record
            for record in self._records.values()
            if record.index_id == index_id and self._scope_allows(record, scope)
        )
        filtered = (record for record in safe if self._filters_allow(record, filters))
        return tuple(sorted(filtered, key=lambda item: (item.asset_id, item.asset_version)))

    def add_usage_signal(self, signal: UsageSignal) -> None:
        self._usage.append(signal)

    def usage_signals(
        self,
        organization_id: str,
        asset_id: str,
    ) -> tuple[UsageSignal, ...]:
        return tuple(
            signal
            for signal in self._usage
            if signal.organization_id == organization_id and signal.asset_id == asset_id
        )

    def mark_deleted(self, organization_id: str, asset_id: str, deleted_at: str) -> None:
        for key, record in tuple(self._records.items()):
            if record.organization_id != organization_id or record.asset_id != asset_id:
                continue
            self._records[key] = replace(record, state="DELETING", deleted_at=deleted_at)

    def reconcile_deleted(self, organization_id: str, asset_id: str) -> int:
        keys = [
            key
            for key, record in self._records.items()
            if record.organization_id == organization_id and record.asset_id == asset_id
        ]
        for key in keys:
            del self._records[key]
        self._usage = [
            signal
            for signal in self._usage
            if not (signal.organization_id == organization_id and signal.asset_id == asset_id)
        ]
        return len(keys)
