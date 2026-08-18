from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from pydantic import ValidationError

from lumi_api.api.v1.brand_registry_schemas import BrandPatchRequest
from lumi_api.brand_rules.contracts import RuleSource
from lumi_api.brand_rules.service import (
    BrandRuleNotFound,
    BrandRulePublicationDenied,
    BrandRuleService,
)
from lumi_api.domain.ids import new_uuid7


@dataclass(frozen=True)
class _RuleSet:
    id: UUID
    brand_id: UUID


@dataclass(frozen=True)
class _Proposal:
    id: UUID
    brand_id: UUID


class _Repository:
    def __init__(self) -> None:
        self.rule_sets: dict[UUID, _RuleSet] = {}
        self.active: dict[UUID, _RuleSet] = {}
        self.proposals: dict[UUID, _Proposal] = {}

    def get_rule_set(self, organization_id: UUID, rule_set_id: UUID):
        del organization_id
        return self.rule_sets.get(rule_set_id)

    def get_active_rule_set(self, organization_id: UUID, brand_id: UUID):
        del organization_id
        return self.active.get(brand_id)

    def get_proposal(self, organization_id: UUID, proposal_id: UUID):
        del organization_id
        return self.proposals.get(proposal_id)

    def next_version(self, organization_id: UUID, brand_id: UUID) -> int:
        del organization_id, brand_id
        return 1

    def save_rule_set(self, value) -> None:
        self.rule_sets[value.id] = value

    def set_active_rule_set(self, organization_id: UUID, brand_id: UUID, rule_set_id: UUID) -> None:
        del organization_id
        self.active[brand_id] = self.rule_sets[rule_set_id]

    def save_proposal(self, value) -> None:
        self.proposals[value.id] = value


def test_brand_patch_requires_an_explicit_change() -> None:
    with pytest.raises(ValidationError, match="BRAND_PATCH_REQUIRES_CHANGE"):
        BrandPatchRequest.model_validate({})


def test_exact_rule_set_and_active_rule_set_reads_are_brand_scoped() -> None:
    organization_id = new_uuid7()
    brand_id = new_uuid7()
    other_brand_id = new_uuid7()
    exact = _RuleSet(id=new_uuid7(), brand_id=brand_id)
    repository = _Repository()
    repository.rule_sets[exact.id] = exact
    repository.active[brand_id] = exact
    service = BrandRuleService(repository)  # type: ignore[arg-type]

    assert service.get_rule_set(
        organization_id=organization_id,
        brand_id=brand_id,
        rule_set_id=exact.id,
    ) is exact
    assert service.get_active_rule_set(
        organization_id=organization_id,
        brand_id=brand_id,
    ) is exact

    with pytest.raises(BrandRuleNotFound):
        service.get_rule_set(
            organization_id=organization_id,
            brand_id=other_brand_id,
            rule_set_id=exact.id,
        )


def test_exact_guide_proposal_read_is_brand_scoped() -> None:
    organization_id = new_uuid7()
    brand_id = new_uuid7()
    proposal = _Proposal(id=new_uuid7(), brand_id=brand_id)
    repository = _Repository()
    repository.proposals[proposal.id] = proposal
    service = BrandRuleService(repository)  # type: ignore[arg-type]

    assert service.get_guide_proposal(
        organization_id=organization_id,
        brand_id=brand_id,
        proposal_id=proposal.id,
    ) is proposal

    with pytest.raises(BrandRuleNotFound):
        service.get_guide_proposal(
            organization_id=organization_id,
            brand_id=new_uuid7(),
            proposal_id=proposal.id,
        )


def test_inferred_rules_cannot_bypass_cited_human_review_path() -> None:
    service = BrandRuleService(_Repository())  # type: ignore[arg-type]
    with pytest.raises(BrandRulePublicationDenied, match="cited guide proposal"):
        service.create_draft(
            organization_id=new_uuid7(),
            brand_id=new_uuid7(),
            source=RuleSource.INFERRED_PROPOSAL,
            token_set=None,  # type: ignore[arg-type]
            asset_set=None,  # type: ignore[arg-type]
            rules=(),
            voice=None,
            visual_style=None,
            created_by="user:test",
        )
