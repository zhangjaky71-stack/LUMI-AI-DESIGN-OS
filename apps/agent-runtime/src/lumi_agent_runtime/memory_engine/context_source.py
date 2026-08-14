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

from .contracts import (
    MemoryAccessContext,
    MemoryActorType,
    MemoryScope,
    MemorySearchQuery,
)
from .retrieval import MemoryRetriever


class MemoryContextSource:
    """NODE-34 source adapter. Memory remains data, never instruction authority."""

    def __init__(
        self,
        retriever: MemoryRetriever,
        *,
        access_for_request: Callable[[ContextRequest], MemoryAccessContext],
    ) -> None:
        self.retriever = retriever
        self.access_for_request = access_for_request

    async def load_system(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        del request
        return ()

    async def load_project(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        del request
        return ()

    async def load_agent(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        del request
        return ()

    async def load_task(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        del request
        return ()

    async def search(self, request: ContextRequest) -> tuple[RetrievalCandidate, ...]:
        access = self.access_for_request(request)
        results = await self.retriever.search(
            MemorySearchQuery(
                access=access,
                text=request.query or request.purpose,
                limit=request.retrieval_limit,
                query_embedding=_query_embedding(
                    request.metadata.get("query_embedding")
                ),
            )
        )
        output: list[RetrievalCandidate] = []
        for result in results:
            record = result.record
            content = json.dumps(
                {
                    "summary": record.summary,
                    "structured": record.content_structured,
                    "kind": record.kind.value,
                    "scope": record.scope_type.value,
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            trusted_project_scope = record.scope_type in {
                MemoryScope.PROJECT,
                MemoryScope.BRAND,
                MemoryScope.ORGANIZATION,
            }
            trusted_origin = record.created_by_type in {
                MemoryActorType.USER,
                MemoryActorType.SYSTEM,
            }
            trust = (
                TrustLevel.TRUSTED_PROJECT
                if trusted_project_scope and trusted_origin
                else TrustLevel.UNTRUSTED_RETRIEVED
            )
            item = ContextItem(
                item_id=f"memory:{record.memory_id}",
                layer=ContextLayer.L4_RETRIEVED,
                kind=ContextKind.MEMORY,
                content=content,
                source=ContextSourceRef(
                    source_type="memory",
                    source_id=str(record.memory_id),
                    version=str(record.version),
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                ),
                trust=trust,
                priority=700,
                metadata={
                    "instruction_authority": "none",
                    "memory_scope": record.scope_type.value,
                    "memory_created_by": record.created_by_type.value,
                    "source_refs": [
                        {
                            "source_type": ref.source_type,
                            "source_id": ref.source_id,
                            "version": ref.version,
                            "content_hash": ref.content_hash,
                        }
                        for ref in record.source_refs
                    ],
                },
            )
            output.append(
                RetrievalCandidate(
                    item=item,
                    organization_id=str(request.organization_id),
                    project_id=str(request.project_id),
                    lexical_score=result.lexical_score,
                    semantic_score=result.semantic_score,
                    authority_score=result.scope_score,
                    recency_score=result.freshness_score,
                )
            )
        return tuple(output)


def _query_embedding(value: object) -> tuple[float, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        raise ValueError("MEMORY_CONTEXT_QUERY_EMBEDDING_INVALID")
    return tuple(float(item) for item in value)
