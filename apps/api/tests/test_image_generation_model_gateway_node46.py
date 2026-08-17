from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

from lumi_image_generation import (
    GatewayRequest,
    GenerationMode,
    OutputRequirements,
    PromptBlocks,
    QualityProfile,
)
from lumi_api.image_generation.model_gateway_adapter import (
    ModelGatewayImageAdapter,
    to_model_request,
)
from lumi_model_gateway.gateway import ModelGateway
from lumi_model_gateway.memory import (
    MemoryBudgetPort,
    MemoryCostTelemetryPort,
    MemoryHealthPort,
    MemoryPaidSideEffectPort,
)
from lumi_model_gateway.mock_provider import MockProvider
from lumi_model_gateway.models import Capability
from lumi_model_gateway.routing import ModelRouter, ProviderRegistry


def request(mode: GenerationMode = GenerationMode.TEXT_TO_IMAGE) -> GatewayRequest:
    operation = uuid4()
    return GatewayRequest(
        request_id=uuid4(),
        organization_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        root_operation_id=uuid4(),
        variant_operation_id=operation,
        generation_id=uuid4(),
        variant_index=1,
        mode=mode,
        prompt=PromptBlocks("o", "c", "v", (), (), (), "8x8", "image-prompt-v1"),
        references=(),
        target_width=8,
        target_height=8,
        quality_profile=QualityProfile.BALANCED,
        budget_limit_usd=Decimal("1"),
        constraints=(),
        output_requirements=OutputRequirements(),
        seed=7,
        agent_run_id=None,
    )


def gateway() -> ModelGateway:
    provider = MockProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    health = MemoryHealthPort()
    return ModelGateway(
        registry=registry,
        router=ModelRouter(registry, health),
        budget=MemoryBudgetPort(Decimal("10")),
        telemetry=MemoryCostTelemetryPort(),
        paid_side_effects=MemoryPaidSideEffectPort(),
    )


def test_mode_mapping_preserves_node47_edit_boundary() -> None:
    assert (
        to_model_request(request(GenerationMode.TEXT_TO_IMAGE)).capability
        is Capability.IMAGE_GENERATE
    )
    assert (
        to_model_request(request(GenerationMode.PRODUCT_SCENE)).capability
        is Capability.IMAGE_REFERENCE_CONSISTENCY
    )
    assert (
        to_model_request(request(GenerationMode.TRANSPARENT_ASSET)).capability
        is Capability.IMAGE_TRANSPARENT_BACKGROUND
    )
    capabilities = {
        to_model_request(request(mode)).capability
        for mode in GenerationMode
    }
    assert Capability.IMAGE_EDIT not in capabilities
    assert Capability.IMAGE_MASK_EDIT not in capabilities


def test_current_node22_mock_provider_routes_and_invokes_image_generation() -> None:
    adapter = ModelGatewayImageAdapter(gateway())
    value = request()

    async def run():
        return await adapter.estimate(value), await adapter.invoke(value)

    estimate, result = asyncio.run(run())
    assert estimate.amount_usd == Decimal("0.01")
    assert estimate.provider == "mock"
    assert result.status.value == "COMPLETED"
    assert result.provider == "mock"
    assert result.outputs[0].ref.startswith("fixture://mock/image/")
    assert result.cost_usd == Decimal("0.01")
