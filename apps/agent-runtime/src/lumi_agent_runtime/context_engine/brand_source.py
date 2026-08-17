from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .contracts import (
    ContextItem,
    ContextKind,
    ContextLayer,
    ContextRequest,
    ContextSourceRef,
    InstructionAuthority,
    TrustLevel,
)
from .retrieval import RetrievalCandidate


@dataclass(frozen=True, slots=True)
class BrandContextRecord:
    brand_id: UUID
    rule_set_id: UUID
    rule_set_version: int
    snapshot_hash: str
    content: str


class BrandContextProvider(Protocol):
    async def get_brand_context(
        self,
        organization_id: UUID,
        brand_id: UUID,
    ) -> BrandContextRecord | None: ...


class BrandContextRetrievalSource:
    """Expose exact published BrandContext as trusted project data."""

    def __init__(self, provider: BrandContextProvider) -> None:
        self.provider = provider

    async def search(
        self,
        request: ContextRequest,
    ) -> tuple[RetrievalCandidate, ...]:
        raw_brand_id = request.metadata.get("brand_id")
        if raw_brand_id is None:
            return ()
        try:
            brand_id = UUID(str(raw_brand_id))
        except ValueError:
            return ()
        record = await self.provider.get_brand_context(
            request.organization_id,
            brand_id,
        )
        if record is None:
            return ()
        item = ContextItem(
            item_id=f"brand-rule-set:{record.rule_set_id}",
            layer=ContextLayer.L1_PROJECT,
            kind=ContextKind.BRAND_RULE,
            content=record.content,
            source=ContextSourceRef(
                source_ref=(
                    f"brand-rules://{record.brand_id}/{record.rule_set_id}"
                ),
                source_type="brand_rule_set",
                source_id=str(record.rule_set_id),
                version=f"v{record.rule_set_version}",
                content_hash=record.snapshot_hash,
            ),
            trust=TrustLevel.TRUSTED_PROJECT_DATA,
            instruction_authority=InstructionAuthority.NONE,
            priority=950,
            token_estimate=max(1, len(record.content) // 4),
            relevance_score=1.0,
            freshness_score=1.0,
            pinned=True,
            required=True,
            compressible=False,
            metadata={
                "brand_id": str(record.brand_id),
                "brand_rule_set_id": str(record.rule_set_id),
                "brand_rule_set_version": record.rule_set_version,
            },
        )
        return (
            RetrievalCandidate(
                item=item,
                organization_id=str(request.organization_id),
                project_id=str(request.project_id),
                lexical_score=1.0,
                semantic_score=1.0,
                recency_score=1.0,
                authority_score=1.0,
            ),
        )
