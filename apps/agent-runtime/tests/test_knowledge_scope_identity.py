from __future__ import annotations

import hashlib
import unittest
from uuid import UUID

from lumi_agent_runtime.knowledge_engine import (
    InMemoryKnowledgeRepository,
    KnowledgeAccessContext,
    KnowledgeIndexRequest,
    KnowledgePermissionScope,
    KnowledgeService,
    KnowledgeSourceRef,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeTrust,
)

ORG = UUID("01931000-0000-7000-8000-000000000001")
PROJECT_A = UUID("01931000-0000-7000-8000-000000000002")
PROJECT_B = UUID("01931000-0000-7000-8000-000000000003")


def source(version: str) -> KnowledgeSourceRef:
    return KnowledgeSourceRef(
        source_type=KnowledgeSourceType.ASSET,
        source_id="shared-asset",
        version=version,
        content_hash=hashlib.sha256(f"shared-asset:{version}".encode()).hexdigest(),
    )


def request(project_id: UUID, version: str, text: str) -> KnowledgeIndexRequest:
    return KnowledgeIndexRequest(
        access=KnowledgeAccessContext(
            organization_id=ORG,
            project_id=project_id,
            actor_id="scope-test",
        ),
        source=source(version),
        trust=KnowledgeTrust.USER_CONTENT,
        normalized_text=text,
        project_id=project_id,
        permission_scope=KnowledgePermissionScope.PROJECT,
        index_version="shared-index-v1",
        chunk_size_tokens=100,
        chunk_overlap_tokens=10,
    )


class KnowledgeScopeIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_source_can_exist_in_two_projects_without_cross_supersede(self) -> None:
        repo = InMemoryKnowledgeRepository()
        service = KnowledgeService(repo)
        a1 = await service.index(request(PROJECT_A, "1", "Project A first guidance"))
        b1 = await service.index(request(PROJECT_B, "1", "Project B first guidance"))
        self.assertNotEqual(a1.document_id, b1.document_id)

        a2 = await service.index(request(PROJECT_A, "2", "Project A updated guidance"))
        old_a = await repo.get_document(a1.document_id)
        old_b = await repo.get_document(b1.document_id)
        assert old_a is not None and old_b is not None
        self.assertEqual(old_a.status, KnowledgeStatus.SUPERSEDED)
        self.assertEqual(old_b.status, KnowledgeStatus.READY)
        self.assertNotEqual(a2.document_id, b1.document_id)


if __name__ == "__main__":
    unittest.main()
