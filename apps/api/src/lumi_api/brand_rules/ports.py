from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .contracts import (
    AssetRightsSnapshot,
    BrandGuideProposal,
    BrandRuleSet,
)


class BrandRuleRepository(Protocol):
    def next_version(self, organization_id: UUID, brand_id: UUID) -> int: ...
    def save_rule_set(self, value: BrandRuleSet) -> None: ...
    def get_rule_set(
        self, organization_id: UUID, rule_set_id: UUID
    ) -> BrandRuleSet | None: ...
    def get_active_rule_set(
        self, organization_id: UUID, brand_id: UUID
    ) -> BrandRuleSet | None: ...
    def set_active_rule_set(
        self, organization_id: UUID, brand_id: UUID, rule_set_id: UUID
    ) -> None: ...
    def save_proposal(self, value: BrandGuideProposal) -> None: ...
    def get_proposal(
        self, organization_id: UUID, proposal_id: UUID
    ) -> BrandGuideProposal | None: ...


class AssetRightsReader(Protocol):
    def read(
        self, organization_id: UUID, asset_id: UUID
    ) -> AssetRightsSnapshot: ...
