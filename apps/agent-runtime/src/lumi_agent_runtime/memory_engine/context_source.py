from __future__ import annotations

from .contracts import MemoryAccessContext, MemorySearchRequest
from .engine import MemoryEngine


class MemoryContextRetrievalSource:
    """Projects durable memory into NODE-34 as zero-authority retrieved data."""

    def __init__(self, engine: MemoryEngine) -> None:
        self.engine = engine

    async def search(self, request):
        from lumi_agent_runtime.context_engine.contracts import (
            ContextItem,
            ContextKind,
            ContextLayer,
            ContextSourceRef,
            InstructionAuthority,
            TrustLevel,
        )
        from lumi_agent_runtime.context_engine.retrieval import RetrievalCandidate

        access = MemoryAccessContext(
            organization_id=request.organization_id,
            project_id=request.project_id,
            actor_id="context-engine",
            read_scopes=request.memory_read_scopes,
            write_scopes=(),
            agent_run_id=request.agent_run_id,
            task_id=request.task_id,
        )
        hits = await self.engine.search(
            MemorySearchRequest(
                query=request.query,
                scopes=request.memory_read_scopes,
                limit=request.retrieval_limit,
            ),
            access=access,
        )
        output = []
        for hit in hits:
            record = hit.record
            source = ContextSourceRef(
                source_ref=record.memory_ref,
                source_type="memory",
                source_id=f"{record.scope.permission_key}:{record.memory_key}",
                version=f"r{record.revision}",
                content_hash=record.content_hash,
            )
            item = ContextItem(
                item_id=f"memory:{record.memory_key}:r{record.revision}",
                layer=ContextLayer.L4_RETRIEVED,
                kind=ContextKind.MEMORY,
                content=record.content,
                source=source,
                trust=TrustLevel.UNTRUSTED_RETRIEVED,
                instruction_authority=InstructionAuthority.NONE,
                priority=int(round(record.importance * 1000)),
                relevance_score=hit.rank_score,
                freshness_score=hit.recency_score,
                pinned=False,
                required=False,
                compressible=True,
                metadata={
                    "memory_kind": record.kind.value,
                    "memory_scope": record.scope.permission_key,
                    "memory_confidence": record.confidence,
                    "memory_revision": record.revision,
                    "memory_provenance": list(record.source_refs),
                },
            )
            output.append(
                RetrievalCandidate(
                    item=item,
                    organization_id=str(request.organization_id),
                    project_id=str(request.project_id),
                    lexical_score=hit.lexical_score,
                    semantic_score=hit.rank_score,
                    recency_score=hit.recency_score,
                    authority_score=record.confidence,
                    required_memory_scope=record.scope.permission_key,
                    acl_granted=True,
                )
            )
        return tuple(output)
