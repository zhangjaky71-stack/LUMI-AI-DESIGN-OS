from __future__ import annotations

import os
from decimal import Decimal

import asyncpg
import pytest
from lumi_image_generation.model import (
    GatewayGenerationRequest,
    GatewayGenerationResult,
    GenerationCandidate,
    GenerationJob,
    ImageGenerationSpec,
    OutputRequirements,
    PromptBlocks,
    VariantDecision,
)
from lumi_image_generation.ports import PendingInvocationRecord
from lumi_image_generation.repository import (
    GenerationRepositoryError,
    OperationSemanticConflict,
)
from lumi_worker_media.image_generation_repository import PostgresGenerationRepository

pytestmark = pytest.mark.skipif(
    os.getenv("LUMI_DB_INTEGRATION") != "1",
    reason="set LUMI_DB_INTEGRATION=1 with migrated and seeded local PostgreSQL",
)

ORG = "01900000-0000-7000-8000-000000000001"
PROJECT = "01900000-0000-7000-8000-000000000006"
TASK = "01900000-0000-7000-8000-000000000012"
OPERATION = "71900000-0000-7000-8000-000000000001"
VARIANT_OPERATION = "71900000-0000-7000-8000-000000000002"
GENERATION = "image-generation:" + "a" * 64
CANDIDATE = "image-candidate:" + "b" * 64


def _dsn() -> str:
    value = os.environ["DATABASE_URL"]
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


def _spec(*, content: str = "black coffee cup") -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        purpose="postgres acceptance image",
        mode="TEXT_TO_IMAGE",
        prompt_compilation_ref="prompt:postgres:v1",
        objective="Create a product visual",
        content=content,
        visual_direction="minimal studio",
        aspect_ratio="1:1",
        target_width=1024,
        target_height=1024,
        variant_count=1,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile="HIGH",
        budget_limit_usd=Decimal("1.00"),
        output_requirements=OutputRequirements(format="PNG"),
        code_git_sha="a" * 40,
        agent_run_id=None,
        recipe_version="postgres-v1",
        skill_versions={"image-generation": "v1"},
        seed=None,
    )


def _job(spec: ImageGenerationSpec, *, pending: bool = False) -> GenerationJob:
    candidates = ()
    status = "RUNNING"
    if pending:
        status = "PROVIDER_PENDING"
        candidates = (
            GenerationCandidate(
                candidate_id=CANDIDATE,
                generation_id=GENERATION,
                variant_index=1,
                status="PROVIDER_PENDING",
                provider="openai",
                model="gpt-image-1.5",
                provider_request_id="req_pg_1",
            ),
        )
    return GenerationJob(
        generation_id=GENERATION,
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        semantic_hash=spec.semantic_hash,
        status=status,  # type: ignore[arg-type]
        prompt_hash="c" * 64,
        variant_decision=VariantDecision(
            requested_count=1,
            selected_count=1,
            estimated_cost_per_variant_usd=Decimal("0.12"),
            estimated_total_usd=Decimal("0.12"),
            reason_codes=("BUDGET_ALLOWED",),
        ),
        candidates=candidates,
        created_at="2026-08-19T00:00:00Z",
    )


def _pending(*, provider_request_id: str = "req_pg_1") -> PendingInvocationRecord:
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
            visual_direction="minimal studio",
            brand_constraints=(),
            identity_requirements=(),
            negative_constraints=(),
            output_dimensions="1024x1024",
            template_version="postgres-v1",
        ),
        references=(),
        target_width=1024,
        target_height=1024,
        quality_profile="HIGH",
        budget_limit_usd=Decimal("1.00"),
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
        provider_request_id=provider_request_id,
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


@pytest.fixture(autouse=True)
async def cleanup_generation() -> None:
    connection = await asyncpg.connect(_dsn())
    try:
        await connection.execute(
            "DELETE FROM generations WHERE organization_id = $1 AND operation_id = $2",
            __import__("uuid").UUID(ORG),
            __import__("uuid").UUID(OPERATION),
        )
    finally:
        await connection.close()
    yield
    connection = await asyncpg.connect(_dsn())
    try:
        await connection.execute(
            "DELETE FROM generations WHERE organization_id = $1 AND operation_id = $2",
            __import__("uuid").UUID(ORG),
            __import__("uuid").UUID(OPERATION),
        )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_spec_and_job_round_trip_use_canonical_generations_row() -> None:
    repository = PostgresGenerationRepository(os.environ["DATABASE_URL"])
    spec = _spec()
    job = _job(spec)
    await repository.save_spec(spec)
    await repository.save(job)

    assert await repository.get_spec(ORG, OPERATION) == spec
    assert await repository.get_by_operation(ORG, OPERATION) == job
    assert await repository.get(ORG, GENERATION) == job

    connection = await asyncpg.connect(_dsn())
    try:
        row = await connection.fetchrow(
            """
            SELECT provider, model, capability, status,
                   request_json::text AS request_text,
                   result_json::text AS result_text
            FROM generations
            WHERE organization_id = $1 AND operation_id = $2
            """,
            __import__("uuid").UUID(ORG),
            __import__("uuid").UUID(OPERATION),
        )
    finally:
        await connection.close()
    assert row is not None
    assert row["provider"] == "model-gateway"
    assert row["model"] == "routing-pending"
    assert row["capability"] == "image.generate"
    assert row["status"] == "running"
    assert "image_base64" not in row["result_text"]
    assert "b64_json" not in row["result_text"]
    assert "semantic_hash" in row["request_text"]


@pytest.mark.asyncio
async def test_same_operation_changed_semantics_fails_closed() -> None:
    repository = PostgresGenerationRepository(os.environ["DATABASE_URL"])
    await repository.save_spec(_spec())
    with pytest.raises(OperationSemanticConflict, match="GENERATION_OPERATION_SPEC_CONFLICT"):
        await repository.save_spec(_spec(content="different request"))


@pytest.mark.asyncio
async def test_pending_provider_request_cannot_be_rebound() -> None:
    repository = PostgresGenerationRepository(os.environ["DATABASE_URL"])
    spec = _spec()
    await repository.save_spec(spec)
    await repository.save(_job(spec, pending=True))
    first = _pending()
    await repository.save_pending(first)
    assert await repository.get_pending(ORG, GENERATION, CANDIDATE) == first

    with pytest.raises(
        GenerationRepositoryError,
        match="PENDING_INVOCATION_PROVIDER_REQUEST_CHANGED",
    ):
        await repository.save_pending(_pending(provider_request_id="req_pg_2"))

    await repository.delete_pending(ORG, GENERATION, CANDIDATE)
    assert await repository.get_pending(ORG, GENERATION, CANDIDATE) is None
