from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from lumi_model_gateway.memory import MemoryHealthPort
from lumi_model_gateway.mock_provider import MockProvider
from lumi_model_gateway.models import (
    Capability,
    InputKind,
    ModelInput,
    ModelRequest,
    ProviderModel,
)
from lumi_model_gateway.routing import ModelRouter, ProviderRegistry

ORG = UUID("01910000-0000-7000-8000-000000004701")
OP = UUID("01910000-0000-7000-8000-000000004702")
REQ = UUID("01910000-0000-7000-8000-000000004703")


def _request(required: tuple[str, ...]) -> ModelRequest:
    return ModelRequest(
        request_id=REQ,
        organization_id=ORG,
        operation_id=OP,
        capability=Capability.IMAGE_MASK_EDIT,
        inputs=(ModelInput(InputKind.TEXT, text="edit background only"),),
        budget_limit=Decimal("1"),
        constraints={"required_capabilities": list(required)},
    )


def test_required_capabilities_are_hard_model_filters() -> None:
    provider = MockProvider()
    registry = ProviderRegistry()
    registry.register(provider)
    router = ModelRouter(registry, MemoryHealthPort())

    accepted = router.route(
        _request((Capability.IMAGE_REFERENCE_CONSISTENCY.value,))
    )
    assert accepted.candidates
    assert "required_capabilities_match" in accepted.candidates[0].reason_codes

    impossible = router.route(
        _request((Capability.VIDEO_TEXT_TO_VIDEO.value,))
    )
    assert not impossible.candidates
    assert any(
        "required_capability_missing:video.text_to_video" in reason
        for reason in impossible.rejected_reason_codes
    )


def test_transport_model_must_support_required_capability() -> None:
    class SplitMock(MockProvider):
        def __init__(self) -> None:
            super().__init__()
            image = next(model for model in self._models if model.model == "mock-image-v1")
            restricted = replace(
                image,
                capabilities=frozenset({Capability.IMAGE_MASK_EDIT}),
            )
            helper = ProviderModel(
                provider="mock",
                model="mock-reference-helper",
                capabilities=frozenset({Capability.IMAGE_REFERENCE_CONSISTENCY}),
                quality_score=70,
                latency_score=90,
                paid=False,
                fixed_request_usd=Decimal("0.01"),
            )
            self._models = tuple(
                restricted if model.model == "mock-image-v1" else model
                for model in self._models
            ) + (helper,)

    registry = ProviderRegistry()
    registry.register(SplitMock())
    decision = ModelRouter(registry, MemoryHealthPort()).route(
        _request((Capability.IMAGE_REFERENCE_CONSISTENCY.value,))
    )
    assert not decision.candidates
    assert any(
        "required_capability_missing:image.reference_consistency" in reason
        for reason in decision.rejected_reason_codes
    )
