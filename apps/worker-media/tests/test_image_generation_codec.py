from __future__ import annotations

from decimal import Decimal

import pytest
from lumi_image_generation.model import (
    GatewayGenerationRequest,
    GatewayGenerationResult,
    GenerationCandidate,
    GenerationJob,
    ImageGenerationSpec,
    OutputRequirements,
    PromptBlocks,
    ProviderOutputRef,
    VariantDecision,
)
from lumi_image_generation.ports import PendingInvocationRecord
from lumi_worker_media.image_generation_codec import (
    decode_result_snapshot,
    decode_spec,
    encode_result_snapshot,
    encode_spec,
)

ORG = "11111111-1111-1111-1111-111111111111"
PROJECT = "22222222-2222-2222-2222-222222222222"
TASK = "33333333-3333-3333-3333-333333333333"
OPERATION = "44444444-4444-4444-4444-444444444444"
VARIANT_OPERATION = "55555555-5555-5555-5555-555555555555"
GENERATION = "image-generation:" + "a" * 64
CANDIDATE = "image-candidate:" + "b" * 64


def _spec() -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        purpose="campaign image",
        mode="TEXT_TO_IMAGE",
        prompt_compilation_ref="prompt:test:v1",
        objective="Create a product visual",
        content="black coffee cup",
        visual_direction="minimal",
        aspect_ratio="1:1",
        target_width=1024,
        target_height=1024,
        variant_count=1,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile="HIGH",
        budget_limit_usd=Decimal("1.25"),
        output_requirements=OutputRequirements(format="PNG"),
        code_git_sha="a" * 40,
        agent_run_id=None,
        recipe_version="recipe-v1",
        skill_versions={"image-generation": "v1"},
        seed=None,
    )


def _job() -> GenerationJob:
    return GenerationJob(
        generation_id=GENERATION,
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        semantic_hash=_spec().semantic_hash,
        status="PROVIDER_PENDING",
        prompt_hash="c" * 64,
        variant_decision=VariantDecision(
            requested_count=1,
            selected_count=1,
            estimated_cost_per_variant_usd=Decimal("0.12"),
            estimated_total_usd=Decimal("0.12"),
            reason_codes=("BUDGET_ALLOWED",),
        ),
        candidates=(
            GenerationCandidate(
                candidate_id=CANDIDATE,
                generation_id=GENERATION,
                variant_index=1,
                status="PROVIDER_PENDING",
                provider="openai",
                model="gpt-image-1.5",
                provider_request_id="req_123",
            ),
        ),
        created_at="2026-08-19T00:00:00Z",
    )


def _pending() -> PendingInvocationRecord:
    request = GatewayGenerationRequest(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        root_operation_id=OPERATION,
        variant_operation_id=VARIANT_OPERATION,
        generation_id=GENERATION,
        variant_index=1,
        mode="TEXT_TO_IMAGE",
        prompt=PromptBlocks(
            objective="Create a product visual",
            content="black coffee cup",
            visual_direction="minimal",
            brand_constraints=(),
            identity_requirements=(),
            negative_constraints=(),
            output_dimensions="1024x1024",
            template_version="test-v1",
        ),
        references=(),
        target_width=1024,
        target_height=1024,
        quality_profile="HIGH",
        budget_limit_usd=Decimal("1.25"),
        constraints=(),
        output_requirements=OutputRequirements(format="PNG"),
        seed=None,
        agent_run_id=None,
    )
    result = GatewayGenerationResult(
        status="PENDING",
        provider="openai",
        model="gpt-image-1.5",
        model_revision=None,
        provider_request_id="req_123",
        outputs=(),
        cost_usd=Decimal("0.12"),
        cost_confidence="estimated",
        pricing_snapshot_id="image-price-v1",
        routing_reason_codes=("PROFILE_MATCH",),
        safety_metadata={"blocked": False},
    )
    return PendingInvocationRecord(
        organization_id=ORG,
        generation_id=GENERATION,
        candidate_id=CANDIDATE,
        variant_index=1,
        request=request,
        result=result,
    )


def test_spec_snapshot_round_trip_preserves_semantics_and_decimal() -> None:
    spec = _spec()
    encoded = encode_spec(spec)
    decoded = decode_spec(encoded)
    assert decoded == spec
    assert decoded.budget_limit_usd == Decimal("1.25")
    assert encoded["spec"]["semantic_hash"] == spec.semantic_hash


def test_result_snapshot_round_trip_preserves_pending_provider_identity() -> None:
    job = _job()
    pending = _pending()
    encoded = encode_result_snapshot(job, {CANDIDATE: pending})
    decoded_job, decoded_pending = decode_result_snapshot(encoded)
    assert decoded_job == job
    assert decoded_pending[CANDIDATE] == pending
    assert decoded_pending[CANDIDATE].result.provider_request_id == "req_123"


def test_spec_semantic_hash_tamper_is_rejected() -> None:
    encoded = encode_spec(_spec())
    encoded["spec"]["semantic_hash"] = "d" * 64
    with pytest.raises(ValueError, match="GENERATION_SPEC_SEMANTIC_HASH_MISMATCH"):
        decode_spec(encoded)


def test_snapshot_never_serializes_provider_binary() -> None:
    encoded = encode_result_snapshot(_job(), {CANDIDATE: _pending()})
    text = repr(encoded)
    assert "b64_json" not in text
    assert "image_base64" not in text
    assert "bytes" not in text


def test_success_asset_ref_can_be_persisted_without_binary() -> None:
    pending = _pending()
    succeeded = GatewayGenerationResult(
        status="SUCCEEDED",
        provider="openai",
        model="gpt-image-1.5",
        model_revision=None,
        provider_request_id="req_123",
        outputs=(
            ProviderOutputRef(
                ref="s3://lumi-assets/provider-output/v1/org/op/hash.png",
                mime_type="image/png",
            ),
        ),
        cost_usd=Decimal("0.11"),
        cost_confidence="exact",
        pricing_snapshot_id="image-price-v1",
        routing_reason_codes=("PROFILE_MATCH",),
        safety_metadata={"blocked": False},
    )
    replacement = PendingInvocationRecord(
        organization_id=pending.organization_id,
        generation_id=pending.generation_id,
        candidate_id=pending.candidate_id,
        variant_index=pending.variant_index,
        request=pending.request,
        result=GatewayGenerationResult(
            status="PENDING",
            provider=succeeded.provider,
            model=succeeded.model,
            model_revision=succeeded.model_revision,
            provider_request_id=succeeded.provider_request_id,
            outputs=(),
            cost_usd=succeeded.cost_usd,
            cost_confidence=succeeded.cost_confidence,
            pricing_snapshot_id=succeeded.pricing_snapshot_id,
            routing_reason_codes=succeeded.routing_reason_codes,
            safety_metadata=succeeded.safety_metadata,
        ),
    )
    encoded = encode_result_snapshot(_job(), {CANDIDATE: replacement})
    assert "provider-output/v1" not in repr(encoded)
