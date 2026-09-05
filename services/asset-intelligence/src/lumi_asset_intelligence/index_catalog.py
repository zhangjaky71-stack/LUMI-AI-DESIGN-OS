from __future__ import annotations

from dataclasses import dataclass, replace

from .model import AssetIndexVersion


@dataclass(frozen=True)
class IndexCoverageComparison:
    organization_id: str
    active_index_id: str
    candidate_index_id: str
    active_asset_count: int
    candidate_asset_count: int
    common_asset_count: int
    missing_asset_ids: tuple[str, ...]
    added_asset_ids: tuple[str, ...]
    embedding_space_changed: bool

    @property
    def coverage_ratio(self) -> float:
        if self.active_asset_count == 0:
            return 1.0
        return self.common_asset_count / self.active_asset_count


@dataclass(frozen=True)
class IndexPromotionDecision:
    comparison: IndexCoverageComparison
    approved: bool
    approved_by: str
    reason: str


class IndexCatalogError(ValueError):
    pass


class InMemoryIndexCatalog:
    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], AssetIndexVersion] = {}
        self._active: dict[str, str] = {}

    def register(self, index: AssetIndexVersion) -> None:
        key = (index.organization_id, index.index_id)
        if key in self._versions:
            raise IndexCatalogError("INDEX_ALREADY_EXISTS")
        self._versions[key] = index
        if index.state == "ACTIVE":
            if index.organization_id in self._active:
                raise IndexCatalogError("MULTIPLE_ACTIVE_INDEXES")
            self._active[index.organization_id] = index.index_id

    def mark_ready(self, organization_id: str, index_id: str) -> AssetIndexVersion:
        index = self.get(organization_id, index_id)
        if index.state != "BUILDING":
            raise IndexCatalogError("INDEX_NOT_BUILDING")
        ready = replace(index, state="READY")
        self._versions[(organization_id, index_id)] = ready
        return ready

    def get(self, organization_id: str, index_id: str) -> AssetIndexVersion:
        try:
            return self._versions[(organization_id, index_id)]
        except KeyError as exc:
            raise IndexCatalogError("INDEX_NOT_FOUND") from exc

    def active(self, organization_id: str) -> AssetIndexVersion:
        try:
            index_id = self._active[organization_id]
        except KeyError as exc:
            raise IndexCatalogError("ACTIVE_INDEX_NOT_FOUND") from exc
        return self.get(organization_id, index_id)

    def activate(
        self,
        organization_id: str,
        index_id: str,
        decision: IndexPromotionDecision,
        *,
        activated_at: str,
    ) -> AssetIndexVersion:
        candidate = self.get(organization_id, index_id)
        if candidate.state != "READY":
            raise IndexCatalogError("CANDIDATE_INDEX_NOT_READY")
        if decision.comparison.organization_id != organization_id:
            raise IndexCatalogError("PROMOTION_TENANT_MISMATCH")
        if decision.comparison.candidate_index_id != index_id:
            raise IndexCatalogError("PROMOTION_CANDIDATE_MISMATCH")
        if not decision.approved:
            raise IndexCatalogError("PROMOTION_NOT_APPROVED")
        if not decision.approved_by.strip() or not decision.reason.strip():
            raise IndexCatalogError("PROMOTION_AUDIT_REQUIRED")

        previous_id = self._active.get(organization_id)
        if previous_id is not None:
            previous = self.get(organization_id, previous_id)
            self._versions[(organization_id, previous_id)] = replace(previous, state="RETIRED")

        active = replace(candidate, state="ACTIVE", activated_at=activated_at)
        self._versions[(organization_id, index_id)] = active
        self._active[organization_id] = index_id
        return active


def compare_index_coverage(
    active: AssetIndexVersion,
    candidate: AssetIndexVersion,
    *,
    active_asset_ids: set[str],
    candidate_asset_ids: set[str],
) -> IndexCoverageComparison:
    if active.organization_id != candidate.organization_id:
        raise IndexCatalogError("INDEX_COMPARISON_TENANT_MISMATCH")
    common = active_asset_ids & candidate_asset_ids
    return IndexCoverageComparison(
        organization_id=active.organization_id,
        active_index_id=active.index_id,
        candidate_index_id=candidate.index_id,
        active_asset_count=len(active_asset_ids),
        candidate_asset_count=len(candidate_asset_ids),
        common_asset_count=len(common),
        missing_asset_ids=tuple(sorted(active_asset_ids - candidate_asset_ids)),
        added_asset_ids=tuple(sorted(candidate_asset_ids - active_asset_ids)),
        embedding_space_changed=active.embedding_space_id != candidate.embedding_space_id,
    )
