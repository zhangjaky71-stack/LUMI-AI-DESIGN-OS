from __future__ import annotations

import hashlib
import json
from typing import Callable

from lumi_agent_runtime.context_engine import (
    ContextItem,
    ContextKind,
    ContextLayer,
    ContextRequest,
    ContextSourceRef,
    RetrievalCandidate,
    TrustLevel,
)

from .contracts import KnowledgeAccessContext, KnowledgeSearchQuery, KnowledgeTrust
from .retrieval import KnowledgeRetriever


class KnowledgeContextSource:
    """NODE-34 adapter. Knowledge is evidence, never instruction authority."""

    def __init__(
        self,
        retriever: KnowledgeRetriever,
        *,
        access_for_request: Callable[[ContextRequest], KnowledgeAccessContext],
    ) -> None:
        self.retriever = retriever
        self.access_for_request = access_for_request

    async def load_system(
        self,
        request: ContextRequest,
    ) -> tuple[ContextItem, ...]:
        del request
        return ()

    async def load_project(
        self,
        request: ContextRequest,
    ) -> tuple[ContextItem, ...]:
        del request
        return ()

    async def load_agent(
        self,
        request: ContextRequest,
    ) -> tuple[ContextItem, ...]:
        del request
        return ()

    async def load_task(
        self,
        request: ContextRequest,
    ) -> tuple[ContextItem, ...]:
        del request
        return ()

    async def search(
        self,
        request: ContextRequest,
    ) -> tuple[RetrievalCandidate, ...]:
        access = self.access_for_request(request)
        results = await self.retriever.search(
            KnowledgeSearchQuery(
                access=access,
                text=request.query or request.purpose,
                limit=request.retrieval_limit,
                query_embedding=_query_embedding(
                    request.metadata.get("query_embedding")
                ),
                query_embedding_space_id=_optional_text(
                    request.metadata.get("query_embedding_space_id")
                ),
                expanded_queries=_expanded_queries(
                    request.metadata.get("knowledge_expanded_queries")
                ),
                require_fresh=bool(
                    request.metadata.get("knowledge_require_fresh", False)
                ),
                max_source_age_seconds=_optional_positive_int(
                    request.metadata.get("knowledge_max_source_age_seconds")
                ),
            )
        )
        output: list[RetrievalCandidate] = []
        for result in results:
            chunk = result.chunk
            citation = result.citation
            content = json.dumps(
                {
                    "text": chunk.text,
                    "citation": {
                        "source_type": citation.source_type,
                        "source_id": citation.source_id,
                        "source_version": citation.source_version,
                        "source_hash": citation.source_hash,
                        "document_id": str(citation.document_id),
                        "chunk_id": str(citation.chunk_id),
                        "locator": citation.locator,
                        "title": citation.title,
                        "uri": citation.uri,
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            trust = (
                TrustLevel.TRUSTED_PROJECT
                if chunk.trust == KnowledgeTrust.INTERNAL_DATA
                else TrustLevel.UNTRUSTED_RETRIEVED
            )
            item = ContextItem(
                item_id=f"knowledge:{chunk.chunk_id}",
                layer=ContextLayer.L4_RETRIEVED,
                kind=ContextKind.KNOWLEDGE,
                content=content,
                source=ContextSourceRef(
                    source_type="knowledge_chunk",
                    source_id=str(chunk.chunk_id),
                    version=chunk.source.version,
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                ),
                trust=trust,
                priority=650,
                freshness=result.freshness_score,
                metadata={
                    "instruction_authority": "none",
                    "knowledge_trust": chunk.trust.value,
                    "knowledge_stale": result.stale,
                    "citation_source_type": citation.source_type,
                    "citation_source_id": citation.source_id,
                    "citation_source_version": citation.source_version,
                    "citation_source_hash": citation.source_hash,
                    "citation_title": citation.title,
                    "citation_uri": citation.uri,
                    "document_id": str(citation.document_id),
                    "chunk_id": str(citation.chunk_id),
                    "locator": citation.locator,
                },
            )
            output.append(
                RetrievalCandidate(
                    item=item,
                    organization_id=str(request.organization_id),
                    project_id=str(request.project_id),
                    lexical_score=result.lexical_score,
                    semantic_score=result.semantic_score,
                    authority_score=result.authority_score,
                    recency_score=result.freshness_score,
                )
            )
        return tuple(output)


def _query_embedding(value: object) -> tuple[float, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError("KNOWLEDGE_CONTEXT_QUERY_EMBEDDING_INVALID")
    return tuple(float(item) for item in value)


def _expanded_queries(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("KNOWLEDGE_CONTEXT_EXPANDED_QUERY_INVALID")
    return tuple(str(item).strip() for item in value if str(item).strip())


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed < 1:
        raise ValueError("KNOWLEDGE_CONTEXT_FRESHNESS_WINDOW_INVALID")
    return parsed
