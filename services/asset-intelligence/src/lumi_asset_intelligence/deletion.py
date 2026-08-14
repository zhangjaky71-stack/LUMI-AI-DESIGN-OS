from __future__ import annotations

from dataclasses import dataclass

from .model import AssetIndexRepository


@dataclass(frozen=True)
class DeletionReconciliationResult:
    organization_id: str
    asset_id: str
    removed_analysis_count: int
    reconciled: bool


class AssetIndexDeletionService:
    def __init__(self, repository: AssetIndexRepository) -> None:
        self._repository = repository

    def schedule_delete(
        self,
        organization_id: str,
        asset_id: str,
        *,
        deleted_at: str,
    ) -> None:
        self._repository.mark_deleted(organization_id, asset_id, deleted_at)

    def reconcile(
        self,
        organization_id: str,
        asset_id: str,
    ) -> DeletionReconciliationResult:
        removed = self._repository.reconcile_deleted(organization_id, asset_id)
        return DeletionReconciliationResult(
            organization_id=organization_id,
            asset_id=asset_id,
            removed_analysis_count=removed,
            reconciled=True,
        )
