from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from lumi_image_generation import (
    CandidateStatus,
    CompositeGenerationValidator,
    ConstraintSeverity,
    GenerationConstraint,
    GenerationMode,
    IdentityRequirement,
    ImageGenerationPipeline,
    ImageGenerationPipelineError,
    ImageGenerationSpec,
    ImageReference,
    InMemoryGenerationRepository,
    JobStatus,
    OperationSemanticConflict,
    OutputRequirements,
    QualityProfile,
    ReferenceRole,
    ReferenceSource,
)
from lumi_image_generation.model import AuthorizedReference
from lumi_image_generation.testing import (
    FakeGateway,
    FixtureFetcher,
    MemoryArtifacts,
    MemoryCosts,
    MemoryEvents,
    MemoryStorage,
    MemoryWork,
    StaticReferenceAuthorizer,
)
from lumi_image_generation.variants import GenerationBudgetError

NOW = "2026-08-17T13:00:00+00:00"
GIT = "a" * 40


def spec(**updates) -> ImageGenerationSpec:
    base = dict(
        organization_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        purpose="poster hero",
        mode=GenerationMode.TEXT_TO_IMAGE,
        prompt_compilation_ref="prompt-compilation:test-v1",
        objective="Create a premium poster image",
        content="A clean product composition",
        visual_direction="minimal, editorial light",
        aspect_ratio="1:1",
        target_width=8,
        target_height=8,
        variant_count=2,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile=QualityProfile.BALANCED,
        budget_limit_usd=Decimal("1.00"),
        output_requirements=OutputRequirements(),
        code_git_sha=GIT,
        agent_run_id=uuid4(),
        agent_version="creative-director/1.0.0",
        recipe_version="poster/1.0.0",
        skill_versions={"image-generation": "1.0.0"},
        seed=42,
        user_use_declaration="commercial marketing draft",
    )
    base.update(updates)
    return ImageGenerationSpec(**base)


def runtime(value: ImageGenerationSpec, *, gateway: FakeGateway | None = None, refs=()):
    repository = InMemoryGenerationRepository()
    authorizer = StaticReferenceAuthorizer(refs)
    gateway = gateway or FakeGateway()
    fetcher = FixtureFetcher(value.target_width, value.target_height)
    artifacts = MemoryArtifacts()
    costs = MemoryCosts()
    events = MemoryEvents()
    work = MemoryWork()
    pipeline = ImageGenerationPipeline(
        repository=repository,
        references=authorizer,
        gateway=gateway,
        output_fetcher=fetcher,
        storage=MemoryStorage(),
        validator=CompositeGenerationValidator(),
        artifacts=artifacts,
        costs=costs,
        events=events,
        work=work,
    )
    return pipeline, repository, authorizer, gateway, fetcher, artifacts, costs, events, work


@pytest.mark.asyncio
async def test_submit_is_202_style_and_worker_executes_variants_with_provenance() -> None:
    value = spec()
    pipeline, _, _, gateway, _, artifacts, costs, events, work = runtime(value)
    queued = await pipeline.submit(value, now=NOW)
    assert queued.status is JobStatus.QUEUED
    assert gateway.invocations == 0
    assert work.values == [(value.organization_id, queued.generation_id)]

    done = await pipeline.execute(
        organization_id=value.organization_id,
        generation_id=queued.generation_id,
        now=NOW,
    )
    assert done.status is JobStatus.COMPLETED
    assert gateway.invocations == 2
    assert all(item.status is CandidateStatus.READY for item in done.candidates)
    assert len(costs.values) == 2
    assert len(artifacts.values) == 2
    provenance = artifacts.values[0][1]
    assert provenance.prompt_hash == queued.prompt_hash
    assert provenance.provider == "mock"
    assert provenance.model_revision == "rev-1"
    assert provenance.registry_snapshot_id == "registry-v1"
    assert provenance.code_git_sha == GIT
    assert provenance.constraint_snapshot_hash
    assert events.values[0][0] == "generation.started"
    assert events.values[-1][0] == "generation.completed"


@pytest.mark.asyncio
async def test_budget_reduces_only_variant_count_and_can_fail_before_paid_invoke() -> None:
    value = spec(variant_count=4, budget_limit_usd=Decimal("0.025"))
    gateway = FakeGateway(cost="0.01")
    pipeline, _, _, gateway, *_ = runtime(value, gateway=gateway)
    queued = await pipeline.submit(value, now=NOW)
    assert queued.variant_decision.selected_count == 2
    assert "HARD_DIMENSIONS_AND_IDENTITY_UNCHANGED" in queued.variant_decision.reason_codes
    assert gateway.invocations == 0

    impossible = replace(value, operation_id=uuid4(), budget_limit_usd=Decimal("0.001"))
    with pytest.raises(GenerationBudgetError):
        await pipeline.submit(impossible, now=NOW)
    assert gateway.invocations == 0


@pytest.mark.asyncio
async def test_operation_idempotency_replays_semantic_conflict_and_new_operation() -> None:
    value = spec()
    pipeline, _, _, gateway, *_ = runtime(value)
    first = await pipeline.submit(value, now=NOW)
    replay = await pipeline.submit(value, now=NOW)
    assert replay.generation_id == first.generation_id

    changed = replace(value, content="different creative content")
    with pytest.raises(OperationSemanticConflict):
        await pipeline.submit(changed, now=NOW)

    new_operation = replace(value, operation_id=uuid4())
    second = await pipeline.submit(new_operation, now=NOW)
    assert second.generation_id != first.generation_id
    assert second.semantic_hash == first.semantic_hash
    assert gateway.invocations == 0


@pytest.mark.asyncio
async def test_reference_roles_and_rights_fail_before_provider_invoke() -> None:
    asset_id = uuid4()
    reference = ImageReference(
        asset_id,
        "b" * 64,
        ReferenceRole.IDENTITY,
        ReferenceSource.USER_EXPLICIT,
    )
    authorized = AuthorizedReference(
        asset_id,
        "b" * 64,
        ReferenceRole.IDENTITY,
        ReferenceSource.USER_EXPLICIT,
        f"assets/{asset_id}/original.png",
        "owned",
        False,
        "b" * 64,
        "image/png",
    )
    value = spec(mode=GenerationMode.PRODUCT_SCENE, references=(reference,))
    pipeline, _, _, gateway, *_ = runtime(value, refs=(authorized,))
    with pytest.raises(PermissionError):
        await pipeline.submit(value, now=NOW)
    assert gateway.invocations == 0

    missing = replace(value, operation_id=uuid4(), references=())
    with pytest.raises(ImageGenerationPipelineError):
        await pipeline.submit(missing, now=NOW)
    assert gateway.invocations == 0


@pytest.mark.asyncio
async def test_async_poll_uncertainty_stays_pending_then_rights_revocation_rejects() -> None:
    asset_id = uuid4()
    reference = ImageReference(
        asset_id,
        "c" * 64,
        ReferenceRole.IDENTITY,
        ReferenceSource.USER_EXPLICIT,
    )
    authorized = AuthorizedReference(
        asset_id,
        "c" * 64,
        ReferenceRole.IDENTITY,
        ReferenceSource.USER_EXPLICIT,
        f"assets/{asset_id}/original.png",
        "owned",
        True,
        "c" * 64,
        "image/png",
    )
    value = spec(mode=GenerationMode.PRODUCT_SCENE, references=(reference,), variant_count=1)
    gateway = FakeGateway()
    gateway.pending = True
    pipeline, _, authorizer, gateway, *_ = runtime(value, gateway=gateway, refs=(authorized,))
    queued = await pipeline.submit(value, now=NOW)
    pending = await pipeline.execute(
        organization_id=value.organization_id,
        generation_id=queued.generation_id,
        now=NOW,
    )
    assert pending.status is JobStatus.PROVIDER_PENDING

    gateway.poll_raises = True
    deferred = await pipeline.resume_pending(
        organization_id=value.organization_id,
        generation_id=queued.generation_id,
        now=NOW,
    )
    assert deferred.status is JobStatus.PROVIDER_PENDING
    assert deferred.candidates[0].error_code.startswith("GENERATION_POLL_DEFERRED")

    gateway.poll_raises = False
    authorizer.allowed = False
    rejected = await pipeline.resume_pending(
        organization_id=value.organization_id,
        generation_id=queued.generation_id,
        now=NOW,
    )
    assert rejected.status is JobStatus.FAILED
    assert rejected.candidates[0].status is CandidateStatus.REJECTED
    assert rejected.candidates[0].error_code == "GENERATION_REFERENCE_AUTHORIZATION_REVOKED"


@pytest.mark.asyncio
async def test_corrupt_output_keeps_cost_projection_and_never_creates_artifact() -> None:
    value = spec(variant_count=1)
    pipeline, _, _, _, fetcher, artifacts, costs, *_ = runtime(value)
    fetcher.corrupt = True
    queued = await pipeline.submit(value, now=NOW)
    failed = await pipeline.execute(
        organization_id=value.organization_id,
        generation_id=queued.generation_id,
        now=NOW,
    )
    assert failed.status is JobStatus.FAILED
    assert failed.candidates[0].status is CandidateStatus.FAILED
    assert failed.candidates[0].error_code.startswith("GENERATION_OUTPUT_INVALID")
    assert len(costs.values) == 1
    assert artifacts.values == []


@pytest.mark.asyncio
async def test_hard_postflight_unavailable_and_provider_safety_block_fail_closed() -> None:
    constraint = GenerationConstraint(
        "brand-logo",
        "protected_identity",
        ConstraintSeverity.HARD,
        "d" * 64,
    )
    value = spec(variant_count=1, constraints=(constraint,))
    pipeline, _, _, _, _, artifacts, *_ = runtime(value)
    queued = await pipeline.submit(value, now=NOW)
    rejected = await pipeline.execute(
        organization_id=value.organization_id,
        generation_id=queued.generation_id,
        now=NOW,
    )
    assert rejected.status is JobStatus.FAILED
    assert rejected.candidates[0].status is CandidateStatus.REJECTED
    assert artifacts.values[0][2].hard_failed is True

    safe_spec = spec(variant_count=1)
    gateway = FakeGateway()
    gateway.safety_block = True
    pipeline, _, _, _, _, artifacts, *_ = runtime(safe_spec, gateway=gateway)
    queued = await pipeline.submit(safe_spec, now=NOW)
    rejected = await pipeline.execute(
        organization_id=safe_spec.organization_id,
        generation_id=queued.generation_id,
        now=NOW,
    )
    assert rejected.candidates[0].status is CandidateStatus.REJECTED
    assert any(
        item.reason_code == "GENERATION_PROVIDER_SAFETY_BLOCK"
        for item in artifacts.values[0][2].findings
    )


@pytest.mark.asyncio
async def test_transparent_output_requires_alpha_and_cancel_closes_pending_job() -> None:
    value = spec(
        mode=GenerationMode.TRANSPARENT_ASSET,
        variant_count=1,
        output_requirements=OutputRequirements(transparent_background=True),
    )
    gateway = FakeGateway()
    pipeline, _, _, _, fetcher, *_ = runtime(value, gateway=gateway)
    fetcher.content = __import__("lumi_image_generation.testing", fromlist=["png_bytes"]).png_bytes(
        8, 8, alpha=False
    )
    queued = await pipeline.submit(value, now=NOW)
    failed = await pipeline.execute(
        organization_id=value.organization_id,
        generation_id=queued.generation_id,
        now=NOW,
    )
    assert failed.candidates[0].status is CandidateStatus.FAILED

    pending_value = replace(value, operation_id=uuid4())
    pending_gateway = FakeGateway()
    pending_gateway.pending = True
    pipeline, _, _, pending_gateway, *_ = runtime(pending_value, gateway=pending_gateway)
    queued = await pipeline.submit(pending_value, now=NOW)
    pending = await pipeline.execute(
        organization_id=pending_value.organization_id,
        generation_id=queued.generation_id,
        now=NOW,
    )
    cancelled = await pipeline.cancel(
        organization_id=pending_value.organization_id,
        generation_id=pending.generation_id,
        now=NOW,
    )
    assert cancelled.status is JobStatus.CANCELLED
    assert pending_gateway.cancelled is True
