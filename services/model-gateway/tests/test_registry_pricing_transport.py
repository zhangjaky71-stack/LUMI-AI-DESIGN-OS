from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from lumi_model_gateway.memory import MemoryHealthPort
from lumi_model_gateway.models import (
    Capability,
    InputKind,
    ModelInput,
    ModelRequest,
    RoutingHints,
)
from lumi_model_gateway.openai_adapter import OpenAIResponsesAdapter
from lumi_model_gateway.registry import CapabilityRegistry
from lumi_model_gateway.registry_projection import (
    provider_model_from_record,
)
from lumi_model_gateway.registry_seed import load_seed_snapshot
from lumi_model_gateway.routing import ModelRouter, ProviderRegistry
from lumi_model_gateway.secrets import MappingSecretProvider

ROOT = Path(__file__).resolve().parents[3]
ORG = UUID("01910000-0000-7000-8000-000000000531")
REQ = UUID("01910000-0000-7000-8000-000000000532")
OP = UUID("01910000-0000-7000-8000-000000000533")
AT = datetime(2026, 8, 16, tzinfo=UTC)


def request(capability: Capability) -> ModelRequest:
    return ModelRequest(
        request_id=REQ,
        organization_id=ORG,
        operation_id=OP,
        capability=capability,
        inputs=(
            ModelInput(
                kind=InputKind.TEXT,
                text="design a premium landing page",
            ),
        ),
        budget_limit=Decimal("1"),
        constraints={"max_output_tokens": 100},
        routing_hints=RoutingHints(
            preferred_models=("gpt-5.6-sol",),
        ),
    )


def build_router() -> ModelRouter:
    snapshot = load_seed_snapshot(ROOT)
    catalog = CapabilityRegistry(snapshot)
    transports = ProviderRegistry()
    transports.register(
        OpenAIResponsesAdapter(
            MappingSecretProvider({})
        )
    )
    return ModelRouter(
        transports,
        MemoryHealthPort(),
        catalog,
    )


def test_registry_projects_openai_token_prices_with_provenance() -> None:
    snapshot = load_seed_snapshot(ROOT)
    record = snapshot.models["openai:gpt-5.6-sol"]
    projected = provider_model_from_record(
        record,
        registry_snapshot_id=snapshot.snapshot_id,
        pricing_at=AT,
    )
    assert projected.input_usd_per_million == Decimal("5.0")
    assert projected.output_usd_per_million == Decimal("30.0")
    assert projected.pricing_snapshot_id is not None
    assert len(projected.pricing_snapshot_ids) == 2
    assert projected.registry_snapshot_id == snapshot.snapshot_id
    assert projected.model_revision_id == record.revision_id


def test_registry_routing_uses_known_token_cost() -> None:
    decision = build_router().route(
        request(Capability.LLM_REASONING)
    )
    assert decision.candidates
    candidate = decision.candidates[0]
    assert candidate.model.provider == "openai"
    assert candidate.estimate.amount_usd is not None
    assert candidate.estimate.pricing_snapshot_id is not None
    assert candidate.estimate.detail["pricing_snapshot_ids"]
    assert (
        candidate.estimate.detail["registry_snapshot_id"]
        == decision.registry_snapshot_id
    )


def test_catalog_capability_without_transport_fails_closed() -> None:
    decision = build_router().route(
        request(Capability.IMAGE_GENERATE)
    )
    assert decision.candidates == ()
    assert any(
        reason.endswith(":adapter_capability_unavailable")
        and reason.startswith("openai/")
        for reason in decision.rejected_reason_codes
    )
