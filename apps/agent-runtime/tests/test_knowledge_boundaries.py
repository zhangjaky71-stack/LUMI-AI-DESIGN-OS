from __future__ import annotations

import hashlib
import unittest
from uuid import UUID

from lumi_agent_runtime.context_engine import ContextLayer, ContextRequest, LayerBudget
from lumi_agent_runtime.knowledge_engine import (
    InMemoryKnowledgeRepository,
    KnowledgeAccessContext,
    KnowledgeContextSource,
    KnowledgeIndexRequest,
    KnowledgePermissionScope,
    KnowledgeRetriever,
    KnowledgeService,
    KnowledgeSourceRef,
    KnowledgeSourceType,
    KnowledgeTrust,
)

ORG = UUID("01932000-0000-7000-8000-000000000001")
PROJECT = UUID("01932000-0000-7000-8000-000000000002")
RUN = UUID("01932000-0000-7000-8000-000000000003")


def access() -> KnowledgeAccessContext:
    return KnowledgeAccessContext(
        organization_id=ORG,
        project_id=PROJECT,
        actor_id="boundary-test",
    )


def source() -> KnowledgeSourceRef:
    return KnowledgeSourceRef(
        source_type=KnowledgeSourceType.TEXT,
        source_id="configuration-boundary",
        version="1",
        content_hash=hashlib.sha256(b"configuration-boundary").hexdigest(),
    )


def index_request(*, embedding_space_id: str | None) -> KnowledgeIndexRequest:
    return KnowledgeIndexRequest(
        access=access(),
        source=source(),
        trust=KnowledgeTrust.USER_CONTENT,
        normalized_text="Stable lexical source about checkout latency.",
        project_id=PROJECT,
        permission_scope=KnowledgePermissionScope.PROJECT,
        parser_version="native-v1",
        chunker_version="structure-window-v1",
        index_version="fixed-index-v1",
        embedding_space_id=embedding_space_id,
        chunk_size_tokens=100,
        chunk_overlap_tokens=10,
    )


class KnowledgeBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_index_version_rejects_configuration_drift(self) -> None:
        repository = InMemoryKnowledgeRepository()
        service = KnowledgeService(repository)
        await service.index(index_request(embedding_space_id=None))
        with self.assertRaisesRegex(
            ValueError,
            "KNOWLEDGE_INDEX_VERSION_CONFIGURATION_CONFLICT",
        ):
            await service.index(index_request(embedding_space_id="new-space"))

    async def test_context_embedding_without_space_falls_back_to_lexical(self) -> None:
        repository = InMemoryKnowledgeRepository()
        service = KnowledgeService(repository)
        await service.index(index_request(embedding_space_id=None))
        context_source = KnowledgeContextSource(
            KnowledgeRetriever(repository),
            access_for_request=lambda _: access(),
        )
        request = ContextRequest(
            organization_id=ORG,
            project_id=PROJECT,
            agent_run_id=RUN,
            task_id=None,
            agent_ref="researcher@1",
            purpose="knowledge-fallback",
            query="checkout latency",
            max_input_tokens=1200,
            response_reserve_tokens=300,
            layer_budgets=(
                LayerBudget(ContextLayer.L0_SYSTEM, 100),
                LayerBudget(ContextLayer.L1_PROJECT, 100),
                LayerBudget(ContextLayer.L2_AGENT, 100),
                LayerBudget(ContextLayer.L3_TASK, 100),
                LayerBudget(ContextLayer.L4_RETRIEVED, 300),
            ),
            metadata={"query_embedding": [1.0, 0.0]},
        )
        rows = await context_source.search(request)
        self.assertTrue(rows)
        self.assertEqual(rows[0].semantic_score, 0.0)
        self.assertGreater(rows[0].lexical_score, 0.0)


if __name__ == "__main__":
    unittest.main()
