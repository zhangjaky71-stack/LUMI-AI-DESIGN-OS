from datetime import datetime, timezone
from uuid import UUID

import pytest

from lumi_agent_runtime.knowledge_engine import (
    KnowledgeIngestRequest,
    KnowledgeSourceType,
    SourceSection,
)


def test_brand_permission_scope_must_bind_same_brand_id() -> None:
    with pytest.raises(ValueError, match="KNOWLEDGE_BRAND_SCOPE_MISMATCH"):
        KnowledgeIngestRequest(
            source_type=KnowledgeSourceType.BRAND_GUIDE,
            source_ref="asset://brand-guide",
            title="Brand guide",
            parser_version="native-text-v1",
            language="en",
            permission_scope="brand:brand-a",
            sections=(SourceSection(text="Logo rules"),),
            organization_id=UUID("018f4b18-4b9e-7c2b-8a7b-11f5257d1001"),
            project_id=UUID("018f4b18-4b9e-7c2b-8a7b-11f5257d2001"),
            brand_id="brand-b",
            observed_at=datetime(2026, 8, 17, 7, 0, tzinfo=timezone.utc),
        )
