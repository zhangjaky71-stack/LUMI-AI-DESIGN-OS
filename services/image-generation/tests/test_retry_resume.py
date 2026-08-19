from __future__ import annotations

import asyncio
import struct
import zlib
from decimal import Decimal

import pytest
from lumi_image_generation.errors import ImageGenerationTransientError
from lumi_image_generation.inmemory import (
    InMemoryCostReconciliation,
    InMemoryDurableImageStore,
    InMemoryEventSink,
    InMemoryOutputFetcher,
    StaticReferenceAuthorizer,
)
from lumi_image_generation.model import (
    GatewayGenerationResult,
    ImageGenerationSpec,
    OutputRequirements,
    ProviderOutputRef,
)
from lumi_image_generation.pipeline import ImageGenerationPipeline
from lumi_image_generation.ports import ArtifactCandidateResult, GatewayEstimate
from lumi_image_generation.repository import InMemoryGenerationRepository
from lumi_image_generation.validation import CompositeGenerationValidator

ORG = "11111111-1111-1111-1111-111111111111"
PROJECT = "22222222-2222-2222-2222-222222222222"
TASK = "33333333-3333-3333-3333-333333333333"
OPERATION = "44444444-4444-4444-4444-444444444444"
NOW = "2026-08-19T00:00:00Z"


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def _png() -> bytes:
    raw = b"\x00\x00\x00\x00\xff"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def _spec() -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        purpose="retry acceptance",
        mode="TEXT_TO_IMAGE",
        prompt_compilation_ref="prompt:retry:v1",
        objective="Create a product image",
        content="black cup",
        visual_direction="minimal",
        aspect_ratio="1:1",
        target_width=1,
        target_height=1,
        variant_count=1,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile="HIGH",
        budget_limit_usd=Decimal("1.00"),
        output_requirements=OutputRequirements(format="PNG"),
        code_git_sha="a" * 40,
    )


class _TransientThenSuccessGateway:
    def __init__(self) -> None:
        self.estimate_count = 0
        self.invoke_count = 0

    async def estimate(self, request: object) -> GatewayEstimate:
        del request
        self.estimate_count += 1
        return GatewayEstimate(
            amount_usd=Decimal("0.10"),
            pricing_snapshot_id="price-v1",
            provider="openai",
            model="gpt-image-1.5",
            routing_reason_codes=("CAPABILITY_MATCH",),
        )

    async def invoke(self, request: object) -> GatewayGenerationResult:
        del request
        self.invoke_count += 1
        if self.invoke_count == 1:
            raise ImageGenerationTransientError(
                "MODEL_GATEWAY_TEMPORARY",
                "temporary private gateway outage",
            )
        return GatewayGenerationResult(
            status="SUCCEEDED",
            provider="openai",
            model="gpt-image-1.5",
            model_revision=None,
            provider_request_id="req_retry_1",
            outputs=(
                ProviderOutputRef(
                    ref="fixture://retry.png",
                    mime_type="image/png",
                ),
            ),
            cost_usd=Decimal("0.10"),
            cost_confidence="exact",
            pricing_snapshot_id="price-v1",
            routing_reason_codes=("CAPABILITY_MATCH",),
            safety_metadata={"blocked": False},
            finish_reason="completed",
        )

    async def poll(self, **kwargs: object) -> GatewayGenerationResult:
        del kwargs
        raise AssertionError("poll not expected")


class _ArtifactPort:
    async def create_candidate(self, **kwargs: object) -> ArtifactCandidateResult:
        del kwargs
        return ArtifactCandidateResult(
            artifact_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            artifact_version_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            status="READY",
        )


def test_running_job_continues_only_missing_variant_after_transient() -> None:
    repository = InMemoryGenerationRepository()
    gateway = _TransientThenSuccessGateway()
    costs = InMemoryCostReconciliation()
    pipeline = ImageGenerationPipeline(
        repository=repository,
        references=StaticReferenceAuthorizer({}),
        gateway=gateway,  # type: ignore[arg-type]
        output_fetcher=InMemoryOutputFetcher({"fixture://retry.png": _png()}),
        storage=InMemoryDurableImageStore(),
        validator=CompositeGenerationValidator(),
        artifacts=_ArtifactPort(),
        costs=costs,
        events=InMemoryEventSink(),
    )

    with pytest.raises(ImageGenerationTransientError):
        asyncio.run(pipeline.start(_spec(), created_at=NOW))

    running = asyncio.run(repository.get_by_operation(ORG, OPERATION))
    assert running is not None
    assert running.status == "RUNNING"
    assert running.candidates == ()

    completed = asyncio.run(pipeline.start(_spec(), created_at=NOW))
    assert completed.status == "COMPLETED"
    assert completed.candidates[0].status == "READY"
    assert gateway.estimate_count == 1
    assert gateway.invoke_count == 2
    assert len(costs.records) == 1
