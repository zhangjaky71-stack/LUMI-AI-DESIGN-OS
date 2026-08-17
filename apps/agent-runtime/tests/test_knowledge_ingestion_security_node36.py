from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from lumi_agent_runtime.knowledge_engine import (
    KnowledgeAccessContext,
    KnowledgeEngine,
    KnowledgeIngestionService,
    KnowledgeSourceInput,
    KnowledgeSourceType,
)

ORG = UUID("018f4b18-4b9e-7c2b-8a7b-11f5257d4001")
OTHER_ORG = UUID("018f4b18-4b9e-7c2b-8a7b-11f5257d4002")
PROJECT = UUID("018f4b18-4b9e-7c2b-8a7b-11f5257d4003")
NOW = datetime(2026, 8, 17, 7, 0, tzinfo=timezone.utc)


class NeverCalledExtractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract_native(self, source, *, access):
        del source, access
        self.calls += 1
        raise AssertionError("extractor must not run for unauthorized source")

    async def extract_ocr(self, source, *, access):
        del source, access
        self.calls += 1
        raise AssertionError("extractor must not run for unauthorized source")


@pytest.mark.asyncio
async def test_cross_tenant_source_is_rejected_before_extractor_io() -> None:
    extractor = NeverCalledExtractor()
    service = KnowledgeIngestionService(KnowledgeEngine(), extractor=extractor)
    access = KnowledgeAccessContext(
        organization_id=ORG,
        project_id=PROJECT,
        actor_id="security-test",
        read_scopes=("project",),
    )
    source = KnowledgeSourceInput(
        source_type=KnowledgeSourceType.UPLOADED_DOCUMENT,
        source_ref="asset://other-tenant-document",
        title="Denied",
        organization_id=OTHER_ORG,
        project_id=PROJECT,
        permission_scope="project",
        observed_at=NOW,
    )
    with pytest.raises(PermissionError, match="KNOWLEDGE_TENANT_DENIED"):
        await service.ingest(access, source)
    assert extractor.calls == 0
