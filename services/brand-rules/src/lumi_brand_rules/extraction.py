from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from .model import BrandRule, BrandRuleError, Severity


@dataclass(frozen=True, slots=True)
class ExtractionCandidate:
    candidate_id: str
    rule: BrandRule
    confidence: float
    citations: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class ExtractionProposal:
    id: str
    organization_id: str
    brand_profile_id: str
    source_asset_id: str
    status: Literal["PROPOSED", "APPROVED", "REJECTED"]
    candidates: tuple[ExtractionCandidate, ...]
    created_at: str
    reviewed_by: str | None = None
    reviewed_at: str | None = None


def create_extraction_proposal(
    *,
    proposal_id: str,
    organization_id: str,
    brand_profile_id: str,
    source_asset_id: str,
    created_at: str,
    candidates: tuple[ExtractionCandidate, ...],
) -> ExtractionProposal:
    normalized: list[ExtractionCandidate] = []
    for candidate in candidates:
        if not 0 <= candidate.confidence <= 1:
            raise BrandRuleError("extraction confidence must be in [0,1]")
        if not candidate.citations:
            raise BrandRuleError("extraction candidate requires source citations")
        if candidate.rule.severity == "HARD":
            raise BrandRuleError("unreviewed extraction cannot propose a HARD rule")
        normalized.append(
            replace(
                candidate,
                rule=replace(
                    candidate.rule,
                    source="INFERRED_PROPOSAL",
                    citations=tuple(candidate.citations),
                ),
            )
        )
    return ExtractionProposal(
        id=proposal_id,
        organization_id=organization_id,
        brand_profile_id=brand_profile_id,
        source_asset_id=source_asset_id,
        status="PROPOSED",
        candidates=tuple(normalized),
        created_at=created_at,
    )


def approve_extraction_proposal(
    proposal: ExtractionProposal,
    *,
    candidate_id: str,
    reviewer: str,
    reviewed_at: str,
    severity: Severity | None = None,
) -> tuple[ExtractionProposal, BrandRule]:
    if proposal.status != "PROPOSED":
        raise BrandRuleError("only PROPOSED extraction can be approved")
    if not reviewer:
        raise BrandRuleError("approval requires reviewer identity")
    candidate = next(
        (item for item in proposal.candidates if item.candidate_id == candidate_id),
        None,
    )
    if candidate is None or not candidate.citations:
        raise BrandRuleError("approved candidate requires source citations")
    approved_rule = replace(
        candidate.rule,
        source="APPROVED_GUIDE_EXTRACTION",
        severity=severity or candidate.rule.severity,
        citations=tuple(candidate.citations),
    )
    approved = replace(
        proposal,
        status="APPROVED",
        reviewed_by=reviewer,
        reviewed_at=reviewed_at,
    )
    return approved, approved_rule
