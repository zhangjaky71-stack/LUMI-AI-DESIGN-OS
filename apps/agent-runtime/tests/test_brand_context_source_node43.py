from __future__ import annotations

import asyncio
from uuid import UUID

from lumi_agent_runtime.context_engine.brand_source import (
    BrandContextRecord,
    BrandContextRetrievalSource,
)
from lumi_agent_runtime.context_engine.contracts import ContextKind, ContextRequest


ORG = UUID("11111111-1111-4111-8111-111111111111")
PROJECT = UUID("22222222-2222-4222-8222-222222222222")
RUN = UUID("77777777-7777-4777-8777-777777777777")
BRAND = UUID("33333333-3333-4333-8333-333333333333")
RULESET = UUID("44444444-4444-4444-8444-444444444444")


class Provider:
    async def get_brand_context(self, organization_id, brand_id):
        assert organization_id == ORG
        assert brand_id == BRAND
        return BrandContextRecord(
            brand_id=BRAND,
            rule_set_id=RULESET,
            rule_set_version=3,
            snapshot_hash="b" * 64,
            content='{"hard_rules":[{"key":"logo-clear-space"}]}',
        )


def test_brand_context_source_pins_exact_ruleset_version():
    source = BrandContextRetrievalSource(Provider())
    request = ContextRequest(
        organization_id=ORG,
        project_id=PROJECT,
        agent_run_id=RUN,
        task_id=None,
        agent_ref="director@1.0.0",
        context_bundle_ref="context-bundle://node43/test",
        objective="Apply the exact approved brand rules.",
        purpose="brand compliance",
        query="brand rules",
        max_input_tokens=4096,
        response_reserve_tokens=512,
        static_prompt_tokens=256,
        layer_budgets=(),
        metadata={"brand_id": str(BRAND)},
    )
    candidates = asyncio.run(source.search(request))
    assert len(candidates) == 1
    item = candidates[0].item
    assert item.kind == ContextKind.BRAND_RULE
    assert item.required is True
    assert item.pinned is True
    assert item.source.version == "v3"
    assert item.source.content_hash == "b" * 64
    assert item.metadata["brand_rule_set_id"] == str(RULESET)
