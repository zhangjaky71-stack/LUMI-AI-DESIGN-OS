from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from lumi_model_gateway.memory import MemoryHealthPort
from lumi_model_gateway.mock_provider import MockProvider
from lumi_model_gateway.models import (
    Capability,
    InputKind,
    ModelInput,
    ModelRequest,
    RoutingHints,
)
from lumi_model_gateway.registry import (
    CapabilityClaim,
    CapabilityRegistry,
    CapabilitySupport,
    ClaimConfidence,
    ModelLifecycle,
    ModelRecord,
    OrganizationModelPolicy,
    RegistrySnapshot,
    registry_checksum,
)
from lumi_model_gateway.routing import ModelRouter, ProviderRegistry

ORG = UUID("01910000-0000-7000-8000-000000000511")
REQ = UUID("01910000-0000-7000-8000-000000000512")
OP = UUID("01910000-0000-7000-8000-000000000513")
NOW = datetime(2026, 8, 16, tzinfo=UTC)


def make_snapshot() -> RegistrySnapshot:
    key = "mock:mock-llm-v1"
    claim = CapabilityClaim(
        model_key=key,
        capability=Capability.LLM_REASONING,
        support=CapabilitySupport.FULL,
        confidence=ClaimConfidence.LIVE_TEST,
        observed_at=NOW,
        source_ref="mock-contract",
    )
    record = ModelRecord(
        model_key=key,
        provider="mock",
        model="mock-llm-v1",
        lifecycle=ModelLifecycle.STABLE,
        route_eligible=True,
        observed_at=NOW,
        source_refs=("mock-contract",),
        claims=(claim,),
        revision_id="revision:mock-v1",
    )
    checksum = registry_checksum({"models": [key], "version": "test-v1"})
    return RegistrySnapshot(
        snapshot_id=f"registry:test-v1:{checksum[:8]}",
        version="test-v1",
        checksum_sha256=checksum,
        observed_at=NOW,
        published_at=NOW,
        models={key: record},
        routing_profiles={},
        source_ref="test",
    )


def request(*, preferred: str | None = None) -> ModelRequest:
    return ModelRequest(
        request_id=REQ,
        organization_id=ORG,
        operation_id=OP,
        capability=Capability.LLM_REASONING,
        inputs=(ModelInput(kind=InputKind.TEXT, text="hello"),),
        budget_limit=Decimal("1"),
        routing_hints=RoutingHints(
            preferred_providers=(() if preferred is None else (preferred,)),
            allow_unknown_cost=True,
        ),
    )


def test_router_uses_pinned_registry_snapshot_and_not_adapter_model_scores() -> None:
    adapters = ProviderRegistry()
    adapters.register(MockProvider())
    catalog = CapabilityRegistry(make_snapshot())
    router = ModelRouter(adapters, MemoryHealthPort(), catalog)

    decision = router.route(request())
    assert decision.registry_snapshot_id == catalog.capture_snapshot().snapshot_id
    assert len(decision.candidates) == 1
    candidate = decision.candidates[0]
    assert candidate.model.registry_snapshot_id == decision.registry_snapshot_id
    assert candidate.model.model_revision_id == "revision:mock-v1"
    assert "quality_not_measured" in candidate.reason_codes
    assert "latency_not_measured" in candidate.reason_codes


def test_org_policy_cannot_be_bypassed_by_provider_preference() -> None:
    adapters = ProviderRegistry()
    adapters.register(MockProvider())
    catalog = CapabilityRegistry(make_snapshot())
    catalog.set_policy(
        OrganizationModelPolicy(
            organization_id=ORG,
            disabled_providers=frozenset({"mock"}),
        )
    )
    router = ModelRouter(adapters, MemoryHealthPort(), catalog)
    decision = router.route(request(preferred="mock"))
    assert decision.candidates == ()


def test_catalog_model_without_adapter_is_explicitly_rejected() -> None:
    snapshot = make_snapshot()
    original = snapshot.models["mock:mock-llm-v1"]
    external = ModelRecord(
        model_key="external:model-v1",
        provider="external",
        model="model-v1",
        lifecycle=ModelLifecycle.STABLE,
        route_eligible=True,
        observed_at=NOW,
        source_refs=("external-docs",),
        claims=(
            CapabilityClaim(
                model_key="external:model-v1",
                capability=Capability.LLM_REASONING,
                support=CapabilitySupport.FULL,
                confidence=ClaimConfidence.VERIFIED_DOCS,
                observed_at=NOW,
                source_ref="external-docs",
            ),
        ),
        revision_id="revision:external-v1",
    )
    checksum = registry_checksum({"models": [original.model_key, external.model_key]})
    expanded = RegistrySnapshot(
        snapshot_id=f"registry:expanded:{checksum[:8]}",
        version="expanded",
        checksum_sha256=checksum,
        observed_at=NOW,
        published_at=NOW,
        models={original.model_key: original, external.model_key: external},
        routing_profiles={},
        source_ref="test",
    )
    adapters = ProviderRegistry()
    adapters.register(MockProvider())
    router = ModelRouter(
        adapters,
        MemoryHealthPort(),
        CapabilityRegistry(expanded),
    )
    decision = router.route(request())
    assert any(
        reason == "external/model-v1:adapter_unavailable"
        for reason in decision.rejected_reason_codes
    )
    assert [item.model.provider for item in decision.candidates] == ["mock"]
