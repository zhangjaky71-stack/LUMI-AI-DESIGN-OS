from __future__ import annotations

import asyncio
import struct
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest
from lumi_artifacts.history import ArtifactHistory
from lumi_asset_intelligence.model import (
    AnalyzerBundleSnapshot,
    AnalyzerModelSnapshot,
    AssetAnalysisRecord,
)
from lumi_asset_intelligence.repository import InMemoryAssetIndexRepository
from lumi_model_gateway import (
    DeliveryState,
    ErrorCategory,
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    MockFailure,
    MockProvider,
    ModelGateway,
    ModelRouter,
    ModelRequest,
    ModelResult,
    RetryPolicy,
)

from lumi_image_generation.artifact_adapter import ArtifactHistoryCandidateAdapter
from lumi_image_generation.asset_intelligence_adapter import (
    AssetIntelligenceReferenceAuthorizer,
    ReferenceAuthorizationError,
)
from lumi_image_generation.hashing import constraint_snapshot_hash
from lumi_image_generation.image_validation import ImageValidationError, validate_provider_image
from lumi_image_generation.inmemory import (
    InMemoryCostReconciliation,
    InMemoryDurableImageStore,
    InMemoryEventSink,
    InMemoryOutputFetcher,
    ScriptedImageGateway,
    StaticReferenceAuthorizer,
)
from lumi_image_generation.model import (
    AuthorizedReference,
    FetchedImage,
    GatewayGenerationRequest,
    GatewayGenerationResult,
    GenerationConstraint,
    IdentityRequirement,
    ImageGenerationSpec,
    ImageReference,
    OutputRequirements,
    ProviderOutputRef,
    ValidationFinding,
)
from lumi_image_generation.model_gateway_adapter import ModelGatewayImageAdapter
from lumi_image_generation.pipeline import ImageGenerationPipeline, ImageGenerationPipelineError
from lumi_image_generation.ports import GatewayEstimate
from lumi_image_generation.repository import (
    InMemoryGenerationRepository,
    OperationSemanticConflict,
)
from lumi_image_generation.validation import (
    CompositeGenerationValidator,
    DelegateValidationResult,
)
from lumi_image_generation.variants import GenerationBudgetError

ORG = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"
OPERATION = "00000000-0000-0000-0000-000000000004"
ASSET = "00000000-0000-0000-0000-000000000101"
INDEX = "asset-index:test:v1"
NOW = "2026-08-14T12:00:00Z"


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def _png(width: int, height: int, *, alpha: bool = True) -> bytes:
    color_type = 6 if alpha else 2
    pixel = b"\x00\x00\x00\xff" if alpha else b"\x00\x00\x00"
    raw = b"".join(b"\x00" + pixel * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def _spec(
    *,
    operation_id: str = OPERATION,
    mode: str = "TEXT_TO_IMAGE",
    variants: int = 1,
    budget: str = "1.00",
    references: tuple[ImageReference, ...] = (),
    constraints: tuple[GenerationConstraint, ...] = (),
    identity: tuple[IdentityRequirement, ...] = (),
    brand_version: str | None = None,
    transparent: bool = False,
) -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=operation_id,
        purpose="product campaign visual",
        mode=mode,  # type: ignore[arg-type]
        prompt_compilation_ref="prompt-compile:fixture:v1",
        objective="Create a premium campaign image",
        content="black ceramic coffee cup on a minimal set",
        visual_direction="minimal editorial lighting",
        aspect_ratio="1:1",
        target_width=2,
        target_height=2,
        variant_count=variants,
        references=references,
        identity_requirements=identity,
        brand_rule_set_version=brand_version,
        constraints=constraints,
        quality_profile="HIGH",
        budget_limit_usd=Decimal(budget),
        output_requirements=OutputRequirements(
            format="PNG",
            transparent_background=transparent,
            exact_dimensions=True,
        ),
        code_git_sha="a" * 40,
        agent_run_id="agent-run-node46",
        recipe_version="recipe-v1",
        skill_versions={"image-generation": "v1"},
        seed=42,
    )


def _estimate(amount: str = "0.01") -> GatewayEstimate:
    return GatewayEstimate(
        amount_usd=Decimal(amount),
        pricing_snapshot_id="mock-price-v1",
        provider="mock",
        model="mock-v1",
        routing_reason_codes=("CAPABILITY_MATCH", "BUDGET_ALLOWED"),
    )


def _result(
    ref: str = "fixture://image/1.png",
    *,
    status: str = "SUCCEEDED",
    provider_request_id: str = "provider-request-1",
    blocked: bool = False,
) -> GatewayGenerationResult:
    outputs = () if status == "PENDING" else (ProviderOutputRef(ref=ref, mime_type="image/png"),)
    return GatewayGenerationResult(
        status=status,  # type: ignore[arg-type]
        provider="mock",
        model="mock-v1",
        model_revision="mock-revision-v1",
        provider_request_id=provider_request_id,
        outputs=outputs,
        cost_usd=Decimal("0.01"),
        cost_confidence="exact",
        pricing_snapshot_id="mock-price-v1",
        routing_reason_codes=("CAPABILITY_MATCH", "PROVIDER_HEALTHY"),
        safety_metadata={"blocked": blocked},
        finish_reason="completed",
        seed=42,
    )


def _pipeline(
    *,
    gateway: ScriptedImageGateway,
    payloads: dict[str, bytes],
    validator: CompositeGenerationValidator | None = None,
    references: StaticReferenceAuthorizer | None = None,
):
    repository = InMemoryGenerationRepository()
    storage = InMemoryDurableImageStore()
    costs = InMemoryCostReconciliation()
    events = InMemoryEventSink()
    history = ArtifactHistory()
    artifacts = ArtifactHistoryCandidateAdapter(history)
    pipeline = ImageGenerationPipeline(
        repository=repository,
        references=references or StaticReferenceAuthorizer({}),
        gateway=gateway,
        output_fetcher=InMemoryOutputFetcher(payloads),
        storage=storage,
        validator=validator or CompositeGenerationValidator(),
        artifacts=artifacts,
        costs=costs,
        events=events,
    )
    return pipeline, repository, storage, costs, events, history, artifacts


def test_success_creates_ready_artifact_cost_and_full_provenance() -> None:
    gateway = ScriptedImageGateway(estimate=_estimate(), results=(_result(),))
    pipeline, _, storage, costs, events, history, artifacts = _pipeline(
        gateway=gateway,
        payloads={"fixture://image/1.png": _png(2, 2)},
    )
    job = asyncio.run(pipeline.start(_spec(), created_at=NOW))
    assert job.status == "COMPLETED"
    assert job.candidates[0].status == "READY"
    assert len(storage.objects) == 1
    assert len(costs.records) == 1
    assert "generation.started" in [event.event_type for event in events.events]
    assert "artifact.version.created" in [event.event_type for event in events.events]

    version_id = job.candidates[0].artifact_version_id
    assert version_id is not None
    assert history.versions[version_id].status == "READY"
    generic = history.provenance[version_id]
    assert generic.provider == "mock"
    assert generic.model == "mock-v1"
    assert generic.prompt_hash == job.prompt_hash

    snapshot_id = job.candidates[0].provenance_snapshot_id
    assert snapshot_id is not None
    full = artifacts.generation_provenance_snapshots[snapshot_id]
    assert full.provider_request_id == "provider-request-1"
    assert full.prompt_compilation_ref == "prompt-compile:fixture:v1"
    assert full.pricing_snapshot_id == "mock-price-v1"
    assert full.cost_usd == Decimal("0.01")
    assert full.routing_reason_codes == ("CAPABILITY_MATCH", "PROVIDER_HEALTHY")
    assert full.width == 2 and full.height == 2
    assert full.code_git_sha == "a" * 40


def test_variant_budget_reduction_does_not_change_hard_output_dimensions() -> None:
    gateway = ScriptedImageGateway(
        estimate=_estimate("0.01"),
        results=(
            _result("fixture://image/1.png", provider_request_id="r1"),
            _result("fixture://image/2.png", provider_request_id="r2"),
        ),
    )
    pipeline, _, _, _, _, _, _ = _pipeline(
        gateway=gateway,
        payloads={
            "fixture://image/1.png": _png(2, 2),
            "fixture://image/2.png": _png(2, 2),
        },
    )
    job = asyncio.run(pipeline.start(_spec(variants=4, budget="0.025"), created_at=NOW))
    assert job.variant_decision.selected_count == 2
    assert job.variant_decision.reason_codes == (
        "VARIANT_COUNT_REDUCED_FOR_BUDGET",
        "HARD_DIMENSIONS_AND_IDENTITY_UNCHANGED",
    )
    invoked = [request for request in gateway.requests if request.variant_index in {1, 2}]
    assert all(request.target_width == 2 and request.target_height == 2 for request in invoked)


def test_budget_insufficient_blocks_before_paid_invoke() -> None:
    gateway = ScriptedImageGateway(estimate=_estimate("0.02"), results=())
    pipeline, *_ = _pipeline(gateway=gateway, payloads={})
    with pytest.raises(GenerationBudgetError):
        asyncio.run(pipeline.start(_spec(budget="0.01"), created_at=NOW))
    assert gateway.invoke_count == 0


def test_same_operation_retry_reuses_job_and_never_reinvokes_provider() -> None:
    gateway = ScriptedImageGateway(estimate=_estimate(), results=(_result(),))
    pipeline, _, _, _, _, _, _ = _pipeline(
        gateway=gateway,
        payloads={"fixture://image/1.png": _png(2, 2)},
    )
    first = asyncio.run(pipeline.start(_spec(), created_at=NOW))
    second = asyncio.run(pipeline.start(_spec(), created_at=NOW))
    assert second == first
    assert gateway.invoke_count == 1


def test_same_operation_changed_semantics_is_rejected() -> None:
    gateway = ScriptedImageGateway(estimate=_estimate(), results=(_result(),))
    pipeline, *_ = _pipeline(
        gateway=gateway,
        payloads={"fixture://image/1.png": _png(2, 2)},
    )
    asyncio.run(pipeline.start(_spec(), created_at=NOW))
    changed = replace(_spec(), content="different semantic request")
    with pytest.raises(OperationSemanticConflict):
        asyncio.run(pipeline.start(changed, created_at=NOW))


def test_new_operation_with_same_semantics_is_not_creative_content_cache() -> None:
    gateway = ScriptedImageGateway(
        estimate=_estimate(),
        results=(
            _result("fixture://image/1.png", provider_request_id="r1"),
            _result("fixture://image/2.png", provider_request_id="r2"),
        ),
    )
    pipeline, *_ = _pipeline(
        gateway=gateway,
        payloads={
            "fixture://image/1.png": _png(2, 2),
            "fixture://image/2.png": _png(2, 2),
        },
    )
    first = _spec()
    second = _spec(operation_id="00000000-0000-0000-0000-000000000005")
    assert first.semantic_hash == second.semantic_hash
    asyncio.run(pipeline.start(first, created_at=NOW))
    asyncio.run(pipeline.start(second, created_at=NOW))
    assert gateway.invoke_count == 2


def test_async_pending_state_survives_and_resumes() -> None:
    pending = _result(status="PENDING", provider_request_id="async-1")
    completed = _result(provider_request_id="async-1")
    gateway = ScriptedImageGateway(
        estimate=_estimate(),
        results=(pending,),
        poll_results=(completed,),
    )
    pipeline, repository, _, costs, _, history, _ = _pipeline(
        gateway=gateway,
        payloads={"fixture://image/1.png": _png(2, 2)},
    )
    started = asyncio.run(pipeline.start(_spec(), created_at=NOW))
    assert started.status == "PROVIDER_PENDING"
    candidate = started.candidates[0]
    assert repository.get_pending(ORG, started.generation_id, candidate.candidate_id) is not None

    resumed = asyncio.run(
        pipeline.resume_pending(
            organization_id=ORG,
            generation_id=started.generation_id,
            completed_at="2026-08-14T12:01:00Z",
        )
    )
    assert resumed.status == "COMPLETED"
    assert resumed.candidates[0].status == "READY"
    assert repository.get_pending(ORG, started.generation_id, candidate.candidate_id) is None
    assert len(costs.records) == 1
    assert history.versions[resumed.candidates[0].artifact_version_id].status == "READY"  # type: ignore[index]


def test_corrupted_provider_output_fails_candidate_but_reconciles_cost() -> None:
    gateway = ScriptedImageGateway(estimate=_estimate(), results=(_result(),))
    pipeline, _, _, costs, _, history, _ = _pipeline(
        gateway=gateway,
        payloads={"fixture://image/1.png": b"not-an-image"},
    )
    job = asyncio.run(pipeline.start(_spec(), created_at=NOW))
    assert job.status == "FAILED"
    assert job.candidates[0].status == "FAILED"
    assert job.candidates[0].error_code is not None
    assert len(costs.records) == 1
    assert not history.versions


def test_transparent_requirement_rejects_png_without_alpha() -> None:
    fetched = FetchedImage(
        source_ref="fixture://rgb.png",
        content=_png(2, 2, alpha=False),
        declared_mime_type="image/png",
    )
    with pytest.raises(ImageValidationError, match="IMAGE_OUTPUT_ALPHA_REQUIRED"):
        validate_provider_image(fetched, _spec(transparent=True))


def test_hard_constraint_validator_unavailable_rejects_artifact() -> None:
    constraint = GenerationConstraint(
        constraint_id="lock-product",
        constraint_type="LOCK_IDENTITY",
        severity="HARD",
        snapshot_hash="b" * 64,
        parameters={"identity_id": "product-1"},
    )
    gateway = ScriptedImageGateway(estimate=_estimate(), results=(_result(),))
    pipeline, _, _, _, _, history, _ = _pipeline(
        gateway=gateway,
        payloads={"fixture://image/1.png": _png(2, 2)},
        validator=CompositeGenerationValidator(),
    )
    job = asyncio.run(pipeline.start(_spec(constraints=(constraint,)), created_at=NOW))
    assert job.status == "FAILED"
    candidate = job.candidates[0]
    assert candidate.status == "REJECTED"
    assert candidate.validation is not None and candidate.validation.hard_failed
    assert history.versions[candidate.artifact_version_id].status == "REJECTED"  # type: ignore[index]


def test_provider_safety_block_is_hard_rejection() -> None:
    gateway = ScriptedImageGateway(estimate=_estimate(), results=(_result(blocked=True),))
    pipeline, *_ = _pipeline(
        gateway=gateway,
        payloads={"fixture://image/1.png": _png(2, 2)},
    )
    job = asyncio.run(pipeline.start(_spec(), created_at=NOW))
    candidate = job.candidates[0]
    assert candidate.status == "REJECTED"
    assert candidate.validation is not None
    assert any(
        finding.reason_code == "GENERATION_PROVIDER_SAFETY_BLOCK"
        for finding in candidate.validation.findings
    )


def test_product_scene_requires_identity_role_before_gateway() -> None:
    reference = ImageReference(
        asset_id=ASSET,
        asset_version="v1",
        role="STYLE",
        source="USER_EXPLICIT",
    )
    authorized = AuthorizedReference(
        asset_id=ASSET,
        asset_version="v1",
        role="STYLE",
        source="USER_EXPLICIT",
        durable_ref=f"asset:{ASSET}@v1",
        rights="USER_OWNED",
        commercial_use_allowed=True,
        checksum_sha256="c" * 64,
        mime_type="image/png",
    )
    gateway = ScriptedImageGateway(estimate=_estimate(), results=())
    pipeline, *_ = _pipeline(
        gateway=gateway,
        payloads={},
        references=StaticReferenceAuthorizer({(ASSET, "v1"): authorized}),
    )
    with pytest.raises(ImageGenerationPipelineError, match="PRODUCT_SCENE_IDENTITY_REFERENCE_REQUIRED"):
        asyncio.run(
            pipeline.start(
                _spec(mode="PRODUCT_SCENE", references=(reference,)),
                created_at=NOW,
            )
        )
    assert gateway.invoke_count == 0


def _asset_record(*, commercial: bool, rights: str) -> AssetAnalysisRecord:
    bundle = AnalyzerBundleSnapshot(
        analyzer_version="asset-analyzer-v1",
        embedding=AnalyzerModelSnapshot(
            provider_id="fixture",
            model_id="embed",
            model_version="v1",
            capability="embedding.multimodal",
            preprocessor_version="v1",
            registry_snapshot_id="registry-v1",
        ),
    )
    return AssetAnalysisRecord(
        analysis_id="asset-analysis:" + "d" * 64,
        organization_id=ORG,
        asset_id=ASSET,
        asset_version="v1",
        project_id=PROJECT,
        brand_id=None,
        index_id=INDEX,
        index_version="v1",
        state="READY",
        checksum_sha256="e" * 64,
        mime_type="image/png",
        media_type="IMAGE",
        rights=rights,  # type: ignore[arg-type]
        commercial_use_allowed=commercial,
        training_authorized=False,
        permission_tags=(),
        preview_ref="preview:asset-101",
        metadata={},
        ocr_blocks=(),
        regions=(),
        semantic_description="black coffee cup",
        visual_tags=("coffee",),
        embedding=(1.0, 0.0),
        perceptual_hash="0f0f0f0f0f0f0f0f",
        language="en",
        analyzer_bundle=bundle,
        created_at=NOW,
    )


def test_asset_intelligence_reference_rights_filter_runs_before_generation() -> None:
    asset_repo = InMemoryAssetIndexRepository()
    asset_repo.upsert_analysis(_asset_record(commercial=False, rights="UNKNOWN"))
    authorizer = AssetIntelligenceReferenceAuthorizer(
        asset_repo,
        active_index_id=INDEX,
        require_commercial_rights=True,
    )
    ref = ImageReference(
        asset_id=ASSET,
        asset_version="v1",
        role="CONTENT",
        source="USER_EXPLICIT",
    )
    with pytest.raises(ReferenceAuthorizationError):
        authorizer.authorize(_spec(references=(ref,)), (ref,))


def test_constraint_snapshot_hash_changes_for_soft_constraint_too() -> None:
    base = _spec()
    soft = GenerationConstraint(
        constraint_id="soft-style",
        constraint_type="LOCK_STYLE",
        severity="SOFT",
        snapshot_hash="f" * 64,
        parameters={"style": "minimal"},
    )
    assert constraint_snapshot_hash(base) != constraint_snapshot_hash(
        _spec(constraints=(soft,))
    )


class PassingIdentityDelegate:
    async def validate_identity(self, **kwargs: object) -> DelegateValidationResult:
        return DelegateValidationResult(
            findings=(
                ValidationFinding(
                    validator="identity-engine",
                    status="PASS",
                    severity="HARD",
                    reason_code="IDENTITY_PASS",
                    score=0.98,
                    threshold=0.90,
                ),
            ),
            snapshot_id="identity-validation:" + "1" * 64,
        )


def test_identity_snapshot_reaches_artifact_and_generation_provenance() -> None:
    identity = IdentityRequirement(
        identity_id="product-black-cup",
        reference_set_version="v3",
        severity="HARD",
        scenario="STRICT_PRESERVE",
    )
    gateway = ScriptedImageGateway(estimate=_estimate(), results=(_result(),))
    validator = CompositeGenerationValidator(identity=PassingIdentityDelegate())
    pipeline, _, _, _, _, history, artifacts = _pipeline(
        gateway=gateway,
        payloads={"fixture://image/1.png": _png(2, 2)},
        validator=validator,
    )
    job = asyncio.run(pipeline.start(_spec(identity=(identity,)), created_at=NOW))
    candidate = job.candidates[0]
    version = history.versions[candidate.artifact_version_id]  # type: ignore[index]
    assert version.identity_validation_snapshot_id == "identity-validation:" + "1" * 64
    snapshot = artifacts.generation_provenance_snapshots[candidate.provenance_snapshot_id]  # type: ignore[index]
    assert snapshot.identity_validation_snapshot_id == version.identity_validation_snapshot_id


class PassthroughPaidGuard:
    async def execute(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        invoke: Callable[[], Awaitable[ModelResult]],
    ) -> ModelResult:
        del request, provider, model
        return await invoke()


def _gateway_request() -> GatewayGenerationRequest:
    spec = _spec()
    from lumi_image_generation.prompt import compile_prompt

    return GatewayGenerationRequest(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        root_operation_id=OPERATION,
        variant_operation_id=OPERATION,
        generation_id="image-generation:" + "a" * 64,
        variant_index=1,
        mode="TEXT_TO_IMAGE",
        prompt=compile_prompt(spec),
        references=(),
        target_width=2,
        target_height=2,
        quality_profile="HIGH",
        budget_limit_usd=Decimal("1"),
        constraints=(),
        output_requirements=spec.output_requirements,
        seed=42,
        agent_run_id=None,
    )


def test_real_model_gateway_429_cross_provider_fallback_is_exposed_in_provenance_reason() -> None:
    primary = MockProvider(
        provider="primary",
        model="image-primary",
        quality_score=95,
        failures=(
            MockFailure(
                category=ErrorCategory.RATE_LIMIT,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            ),
        ),
    )
    fallback = MockProvider(
        provider="fallback",
        model="image-fallback",
        quality_score=85,
    )
    registry = InMemoryProviderRegistry((primary, fallback))
    health = InMemoryProviderHealthRegistry(failure_threshold=1)
    router = ModelRouter(registry=registry, health=health)
    gateway = ModelGateway(
        registry=registry,
        health=health,
        router=router,
        paid_guard=PassthroughPaidGuard(),
        retry_policy=RetryPolicy(
            max_attempts_per_provider=1,
            base_delay_seconds=0,
            max_delay_seconds=0,
            max_elapsed_seconds=1,
        ),
    )
    adapter = ModelGatewayImageAdapter(gateway)
    result = asyncio.run(adapter.invoke(_gateway_request()))
    assert result.status == "SUCCEEDED"
    assert result.provider == "fallback"
    assert "FALLBACK_INDEX:1" in result.routing_reason_codes
    assert primary.descriptor.provider == "primary"
    assert UUID(OPERATION)
