from __future__ import annotations

from lumi_agent_runtime.context_engine.contracts import (
    ContextItem,
    ContextKind,
    ContextLayer,
    ContextSourceRef,
    InstructionAuthority,
    TrustLevel,
)

from .contracts import KnowledgeHit


def hit_to_context_item(hit: KnowledgeHit, *, priority: int = 420) -> ContextItem:
    """Knowledge is always retrieved data, never an instruction source."""
    source = ContextSourceRef(
        source_ref=(
            f"knowledge://{hit.document.organization_id}/"
            f"{hit.document.document_id}/{hit.chunk.chunk_id}"
        ),
        source_type="knowledge",
        source_id=hit.chunk.chunk_id,
        version=hit.chunk.index_version,
        content_hash=hit.chunk.content_hash,
    )
    return ContextItem(
        item_id=f"knowledge:{hit.chunk.chunk_id}",
        layer=ContextLayer.L4_RETRIEVED,
        kind=ContextKind.KNOWLEDGE,
        content=hit.chunk.text,
        source=source,
        trust=TrustLevel.UNTRUSTED_RETRIEVED,
        instruction_authority=InstructionAuthority.NONE,
        priority=priority,
        token_estimate=hit.chunk.token_count,
        relevance_score=hit.rank_score,
        freshness_score=hit.freshness_score,
        metadata={
            "citation_source_ref": hit.citation.source_ref,
            "citation_title": hit.citation.title,
            "citation_page": hit.citation.page,
            "citation_section": hit.citation.section,
            "document_id": hit.document.document_id,
            "chunk_id": hit.chunk.chunk_id,
            "permission_scope": hit.document.permission_scope,
            "stale": hit.stale,
        },
    )
