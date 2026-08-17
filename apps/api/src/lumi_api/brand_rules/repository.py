from __future__ import annotations

from threading import RLock
from uuid import UUID

from .contracts import AssetRightsSnapshot, BrandGuideProposal, BrandRuleSet
from .ports import AssetRightsReader, BrandRuleRepository


class InMemoryBrandRuleRepository(BrandRuleRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self.rule_sets: dict[UUID, BrandRuleSet] = {}
        self.active_by_brand: dict[tuple[UUID, UUID], UUID] = {}
        self.proposals: dict[UUID, BrandGuideProposal] = {}

    def next_version(self, organization_id: UUID, brand_id: UUID) -> int:
        with self._lock:
            versions = [
                item.version
                for item in self.rule_sets.values()
                if item.organization_id == organization_id and item.brand_id == brand_id
            ]
            return max(versions, default=0) + 1

    def save_rule_set(self, value: BrandRuleSet) -> None:
        with self._lock:
            existing = self.rule_sets.get(value.id)
            if existing is not None:
                if existing.snapshot_hash != value.snapshot_hash:
                    raise ValueError("brand rule set snapshot content is immutable")
                if existing.status.value == "PUBLISHED" and existing != value:
                    raise ValueError("published brand rule set is immutable")
                if existing.status.value == "RETIRED" and existing != value:
                    raise ValueError("retired brand rule set is immutable")
            self.rule_sets[value.id] = value

    def get_rule_set(
        self, organization_id: UUID, rule_set_id: UUID
    ) -> BrandRuleSet | None:
        value = self.rule_sets.get(rule_set_id)
        if value is None or value.organization_id != organization_id:
            return None
        return value

    def get_active_rule_set(
        self, organization_id: UUID, brand_id: UUID
    ) -> BrandRuleSet | None:
        rule_set_id = self.active_by_brand.get((organization_id, brand_id))
        if rule_set_id is None:
            return None
        return self.get_rule_set(organization_id, rule_set_id)

    def set_active_rule_set(
        self, organization_id: UUID, brand_id: UUID, rule_set_id: UUID
    ) -> None:
        value = self.get_rule_set(organization_id, rule_set_id)
        if value is None or value.brand_id != brand_id:
            raise ValueError("rule set does not belong to brand")
        self.active_by_brand[(organization_id, brand_id)] = rule_set_id

    def save_proposal(self, value: BrandGuideProposal) -> None:
        with self._lock:
            existing = self.proposals.get(value.id)
            if existing is not None:
                immutable = (
                    existing.organization_id,
                    existing.brand_id,
                    existing.source_asset_id,
                    existing.rules,
                    existing.citations,
                    existing.created_at,
                )
                candidate = (
                    value.organization_id,
                    value.brand_id,
                    value.source_asset_id,
                    value.rules,
                    value.citations,
                    value.created_at,
                )
                if immutable != candidate:
                    raise ValueError("brand guide proposal evidence is immutable")
            self.proposals[value.id] = value

    def get_proposal(
        self, organization_id: UUID, proposal_id: UUID
    ) -> BrandGuideProposal | None:
        value = self.proposals.get(proposal_id)
        if value is None or value.organization_id != organization_id:
            return None
        return value


class InMemoryAssetRightsReader(AssetRightsReader):
    def __init__(self, snapshots: tuple[AssetRightsSnapshot, ...] = ()) -> None:
        self._values = {item.asset_id: item for item in snapshots}

    def put(self, value: AssetRightsSnapshot) -> None:
        self._values[value.asset_id] = value

    def read(
        self, organization_id: UUID, asset_id: UUID
    ) -> AssetRightsSnapshot:
        del organization_id
        return self._values.get(
            asset_id,
            AssetRightsSnapshot(asset_id=asset_id, exists=False, ready=False),
        )
