from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import replace
from decimal import Decimal

import pytest
from lumi_artifacts.history import ArtifactHistory
from lumi_model_gateway import (
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    MockProvider,
    ModelGateway,
    ModelRequest,
    ModelResult,
    ModelRouter,
    RetryPolicy,
)

from lumi_video_generation.artifact_adapter import ArtifactHistoryVideoAdapter
from lumi_video_generation.inmemory import (
    MemoryMediaSandbox,
    MemoryVideoCostLedger,
    MemoryVideoEvents,
    MemoryVideoOutput,
    ScriptedVideoGateway,
)
from lumi_video_generation.media_sandbox import FfmpegArgvCompiler
from lumi_video_generation.model import (
    GatewayEstimate,
    GatewayVideoResult,
    IdentityRequirement,
    ShotSpec,
    ShotValidationReport,
    SourceImageRef,
    StoredVideoClip,
    ValidationFinding,
    VideoProbeResult,
    VideoTaskSpec,
    VideoTimeline,
    TimelineClip,
    TimelineTransition,
    VideoOutputSpec,
)
from lumi_video_generation.model_gateway_adapter import ModelGatewayVideoAdapter, VideoFeatureRegistry
from lumi_video_generation.pipeline import VideoGenerationPipeline
from lumi_video_generation.repository import InMemoryVideoRepository
from lumi_video_generation.storyboard import compile_storyboard
from lumi_video_generation.validation import CompositeVideoValidator

ORG = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"
OPERATION = "00000000-0000-0000-0000-000000000004"
CODE_SHA = "a" * 40


def _source() -> SourceImageRef:
    return SourceImageRef(
        asset_id="asset-source",
        asset_version="v1",
        durable_ref="asset:source@v1",
        checksum_sha256="b" * 64,
        commercial_use_allowed=True,
    )


def _spec(
    *,
    mode: str = "TEXT_TO_VIDEO",
    duration: str = "2",
    shots: tuple[ShotSpec, ...] = (),
    source_images: tuple[SourceImageRef, ...] = (),
    budget: str = "1.00",
    identities: tuple[IdentityRequirement, ...] = (),
    allow_optional_drop: bool = False,
    quality_retry_limit: int = 0,
) -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        mode=mode,  # type: ignore[arg-type]
        prompt="Create a cinematic product video",
        duration_seconds=Decimal(duration),
        aspect_ratio="16:9",
        width=1600,
        height=900,
        fps=24,
        budget_limit_usd=Decimal(budget),
        code_git_sha=CODE_SHA,
        source_images=source_images,
        shots=shots,
        identity_requirements=identities,
        allow_optional_shot_drop=allow_optional_drop,
        quality_retry_limit=quality_retry_limit,
    )


def _clip(name: str, *, duration: str = "2", width: int = 1600, height: int = 900) -> tuple[StoredVideoClip, VideoProbeResult]:
    digest = hashlib.sha256(name.encode()).hexdigest()
    keyframes = (f"asset:keyframe:{name}:0", f"asset:keyframe:{name}:1")
    clip = StoredVideoClip(
        storage_key=f"video/clips/{digest}.mp4",
        checksum_sha256=digest,
        mime_type="video/mp4",
        size_bytes=4096,
        width=width,
        height=height,
        duration_ms=int(Decimal(duration) * Decimal("1000")),
        durable_asset_ref=f"asset:video-clip:{digest}",
        poster_frame_ref=f"asset:poster:{digest}",
        tail_frame_ref=f"asset:tail:{digest}",
        keyframe_refs=keyframes,
    )
    probe = VideoProbeResult(
        decode_ok=True,
        mime_type="video/mp4",
        container="mp4",
        video_codec="h264",
        width=width,
        height=height,
        fps=Decimal("24"),
        duration_seconds=Decimal(duration),
        keyframe_refs=keyframes,
        poster_frame_ref=clip.poster_frame_ref,
        tail_frame_ref=clip.tail_frame_ref,
    )
    return clip, probe


def _estimate(*, amount: str = "0.01", provider: str = "p1", model: str = "video-a") -> GatewayEstimate:
    return GatewayEstimate(
        amount_usd=Decimal(amount),
        provider=provider,
        model=model,
        pricing_snapshot_id="price-v1",
        routing_reason_codes=("CAPABILITY_MATCH",),
    )


def _result(
    status: str,
    *,
    provider: str = "p1",
    model: str = "video-a",
    request_id: str = "job-1",
    output_ref: str | None = None,
    cost: str = "0.01",
) -> GatewayVideoResult:
    return GatewayVideoResult(
        status=status,  # type: ignore[arg-type]
        provider=provider,
        model=model,
        provider_request_id=request_id,
        output_ref=output_ref,
        output_mime_type="video/mp4" if output_ref else None,
        cost_usd=Decimal(cost),
        cost_confidence="EXACT",
        pricing_snapshot_id="price-v1",
        routing_reason_codes=("CAPABILITY_MATCH",),
    )


def _pipeline(
    *,
    gateway: object,
    outputs: dict[str, tuple[StoredVideoClip, VideoProbeResult]],
    validator: object | None = None,
) -> tuple[VideoGenerationPipeline, InMemoryVideoRepository, ArtifactHistory, MemoryVideoCostLedger, MemoryMediaSandbox, MemoryVideoEvents]:
    repository = InMemoryVideoRepository()
    history = ArtifactHistory()
    costs = MemoryVideoCostLedger()
    sandbox = MemoryMediaSandbox()
    events = MemoryVideoEvents()
    pipeline = VideoGenerationPipeline(
        repository=repository,
        gateway=gateway,  # type: ignore[arg-type]
        output=MemoryVideoOutput(outputs),
        validator=validator or CompositeVideoValidator(),  # type: ignore[arg-type]
        artifacts=ArtifactHistoryVideoAdapter(history),
        sandbox=sandbox,
        costs=costs,
        events=events,
    )
    return pipeline, repository, history, costs, sandbox, events


def test_async_single_shot_does_not_poll_inside_start_and_resume_is_one_poll() -> None:
    gateway = ScriptedVideoGateway(
        estimate=_estimate(),
        submits=(_result("PENDING"),),
        polls=(
            _result("PENDING"),
            _result("SUCCEEDED", output_ref="fixture://clip-1"),
        ),
    )
    pipeline, _, history, costs, sandbox, _ = _pipeline(
        gateway=gateway,
        outputs={"fixture://clip-1": _clip("clip-1")},
    )
    job = asyncio.run(pipeline.start(_spec()))
    assert job.status == "WAITING_EXTERNAL"
    assert gateway.poll_count == 0

    job = asyncio.run(pipeline.resume(organization_id=ORG, video_job_id=job.video_job_id))
    assert job.status == "WAITING_EXTERNAL"
    assert gateway.poll_count == 1

    job = asyncio.run(pipeline.resume(organization_id=ORG, video_job_id=job.video_job_id))
    assert job.status == "COMPLETED"
    assert gateway.poll_count == 2
    assert len(costs.records) == 1
    assert sandbox.render_count == 1
    assert history.versions[job.final_artifact_version_id].status == "READY"  # type: ignore[index]
    assert any(edge.type == "COMPOSED_FROM" for edge in history.edges.values())


def test_completed_resume_is_idempotent_for_cost_artifact_and_render() -> None:
    gateway = ScriptedVideoGateway(
        estimate=_estimate(),
        submits=(_result("SUCCEEDED", output_ref="fixture://clip-1"),),
    )
    pipeline, _, history, costs, sandbox, _ = _pipeline(
        gateway=gateway,
        outputs={"fixture://clip-1": _clip("clip-1")},
    )
    job = asyncio.run(pipeline.start(_spec()))
    versions = len(history.versions)
    job2 = asyncio.run(pipeline.resume(organization_id=ORG, video_job_id=job.video_job_id))
    assert job2 == job
    assert len(history.versions) == versions
    assert len(costs.records) == 1
    assert sandbox.render_count == 1


def test_two_shot_storyboard_creates_clip_lineage_and_auto_previous_tail() -> None:
    shots = (
        ShotSpec(shot_id="s1", duration_seconds=Decimal("1"), prompt="first"),
        ShotSpec(shot_id="s2", duration_seconds=Decimal("1"), prompt="second"),
    )
    gateway = ScriptedVideoGateway(
        estimate=_estimate(),
        submits=(
            _result("SUCCEEDED", request_id="s1", output_ref="fixture://s1"),
            _result("SUCCEEDED", request_id="s2", output_ref="fixture://s2"),
        ),
    )
    pipeline, _, history, costs, sandbox, _ = _pipeline(
        gateway=gateway,
        outputs={"fixture://s1": _clip("s1", duration="1"), "fixture://s2": _clip("s2", duration="1")},
    )
    job = asyncio.run(pipeline.start(_spec(mode="STORYBOARD_MULTI_SHOT", shots=shots)))
    assert job.status == "COMPLETED"
    assert len(costs.records) == 2
    assert sandbox.last_timeline is not None
    assert len(sandbox.last_timeline.clips) == 2
    clip_versions = [item.clip_artifact_version_id for item in job.shots]
    composed = [edge for edge in history.edges.values() if edge.type == "COMPOSED_FROM"]
    assert {edge.from_version_id for edge in composed} == set(clip_versions)
    second_provenance = [record for record in history.provenance.values() if record.provider == "p1" and record.provider_request_id == "s2"]
    assert second_provenance
    assert clip_versions[0] in second_provenance[0].input_artifact_version_ids


def test_identity_validator_unavailable_rejects_paid_shot_and_keeps_cost() -> None:
    gateway = ScriptedVideoGateway(
        estimate=_estimate(),
        submits=(_result("SUCCEEDED", output_ref="fixture://identity"),),
    )
    identity = IdentityRequirement(identity_id="product", reference_set_version="v1")
    pipeline, _, history, costs, sandbox, _ = _pipeline(
        gateway=gateway,
        outputs={"fixture://identity": _clip("identity")},
    )
    job = asyncio.run(pipeline.start(_spec(identities=(identity,), quality_retry_limit=0)))
    assert job.status == "FAILED"
    assert len(costs.records) == 1
    assert sandbox.render_count == 0
    attempt_id = job.shots[0].clip_artifact_version_id
    assert attempt_id is not None
    assert history.versions[attempt_id].status == "REJECTED"


class RejectThenPassValidator:
    def __init__(self) -> None:
        self.calls = 0

    async def validate_shot(self, **kwargs: object) -> ShotValidationReport:
        del kwargs
        self.calls += 1
        if self.calls == 1:
            return ShotValidationReport(
                decision="REJECT",
                findings=(ValidationFinding(
                    validator="fixture",
                    status="FAIL",
                    severity="HARD",
                    reason_code="IDENTITY_DRIFT",
                ),),
            )
        return ShotValidationReport(decision="PASS", findings=())

    async def validate_final(self, **kwargs: object) -> ShotValidationReport:
        del kwargs
        return ShotValidationReport(decision="PASS", findings=())


def test_quality_retry_uses_new_paid_operation_excludes_first_provider_and_keeps_attempt_artifacts() -> None:
    gateway = ScriptedVideoGateway(
        estimate=_estimate(),
        submits=(
            _result("SUCCEEDED", provider="p1", model="video-a", request_id="try-1", output_ref="fixture://bad"),
            _result("SUCCEEDED", provider="p2", model="video-b", request_id="try-2", output_ref="fixture://good"),
        ),
    )
    pipeline, _, history, costs, _, events = _pipeline(
        gateway=gateway,
        outputs={"fixture://bad": _clip("bad"), "fixture://good": _clip("good")},
        validator=RejectThenPassValidator(),
    )
    job = asyncio.run(pipeline.start(_spec(quality_retry_limit=1)))
    assert job.status == "COMPLETED"
    runtime = job.shots[0]
    assert runtime.attempt_count == 1
    assert len(runtime.attempt_artifact_version_ids) == 2
    assert runtime.attempt_artifact_version_ids[0] != runtime.attempt_artifact_version_ids[1]
    assert history.versions[runtime.attempt_artifact_version_ids[0]].status == "REJECTED"
    assert history.versions[runtime.attempt_artifact_version_ids[1]].status == "READY"
    assert len(costs.records) == 2
    assert len(set(costs.records)) == 2
    assert any(exclusion == ("p1:video-a",) for exclusion in gateway.exclusions)
    assert any(event[0] == "video_generation.shot_quality_retry" for event in events.events)


def test_optional_shot_can_be_explicitly_dropped_and_final_is_partial() -> None:
    shots = (
        ShotSpec(shot_id="required", duration_seconds=Decimal("1"), prompt="required"),
        ShotSpec(shot_id="optional", duration_seconds=Decimal("1"), prompt="optional", optional=True),
    )
    gateway = ScriptedVideoGateway(
        estimate=_estimate(),
        submits=(
            _result("SUCCEEDED", request_id="required", output_ref="fixture://required"),
            _result("FAILED", request_id="optional"),
        ),
    )
    pipeline, _, _, costs, sandbox, _ = _pipeline(
        gateway=gateway,
        outputs={"fixture://required": _clip("required", duration="1")},
    )
    job = asyncio.run(pipeline.start(_spec(
        mode="STORYBOARD_MULTI_SHOT",
        shots=shots,
        allow_optional_drop=True,
        quality_retry_limit=0,
    )))
    assert job.status == "PARTIAL"
    assert job.shots[1].status == "DROPPED"
    assert len(costs.records) == 2
    assert sandbox.last_timeline is not None and len(sandbox.last_timeline.clips) == 1


def test_task_budget_is_cumulative_across_shots() -> None:
    shots = (
        ShotSpec(shot_id="s1", duration_seconds=Decimal("1"), prompt="one"),
        ShotSpec(shot_id="s2", duration_seconds=Decimal("1"), prompt="two"),
    )
    gateway = ScriptedVideoGateway(
        estimate=_estimate(amount="0.60"),
        submits=(_result("SUCCEEDED", output_ref="fixture://s1", cost="0.60"),),
    )
    pipeline, _, _, _, _, _ = _pipeline(
        gateway=gateway,
        outputs={"fixture://s1": _clip("s1", duration="1")},
    )
    job = asyncio.run(pipeline.start(_spec(mode="STORYBOARD_MULTI_SHOT", shots=shots, budget="1.00")))
    assert job.status == "FAILED"
    assert job.error_code == "VIDEO_TASK_BUDGET_EXCEEDED"
    assert gateway.submit_count == 1


def test_cancel_external_wait_does_not_retry() -> None:
    gateway = ScriptedVideoGateway(
        estimate=_estimate(),
        submits=(_result("PENDING"),),
    )
    pipeline, _, _, costs, _, _ = _pipeline(gateway=gateway, outputs={})
    job = asyncio.run(pipeline.start(_spec(quality_retry_limit=2)))
    cancelled = asyncio.run(pipeline.cancel(organization_id=ORG, video_job_id=job.video_job_id))
    assert cancelled.status == "CANCELLED"
    assert gateway.cancel_count == 1
    assert gateway.submit_count == 1
    assert len(costs.records) == 1


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


def _real_gateway(*providers: MockProvider) -> ModelGateway:
    registry = InMemoryProviderRegistry(providers)
    health = InMemoryProviderHealthRegistry(failure_threshold=2)
    return ModelGateway(
        registry=registry,
        health=health,
        router=ModelRouter(registry=registry, health=health),
        paid_guard=PassthroughPaidGuard(),
        retry_policy=RetryPolicy(
            max_attempts_per_provider=1,
            base_delay_seconds=0,
            max_delay_seconds=0,
            max_elapsed_seconds=1,
        ),
    )


def test_real_model_gateway_video_async_submit_poll_poll() -> None:
    gateway = _real_gateway(MockProvider(provider="mock", model="video-v1", quality_score=90))
    adapter = ModelGatewayVideoAdapter(gateway)
    shot = compile_storyboard(_spec()).shots[0]
    pending = asyncio.run(adapter.submit(spec=_spec(), shot=shot, continuity_refs=()))
    assert pending.status == "PENDING"
    from lumi_video_generation.model import ProviderJobRecord

    record = ProviderJobRecord(
        organization_id=ORG,
        video_job_id="job",
        shot_id=shot.shot.shot_id,
        paid_operation_id=shot.paid_operation_id,
        request_hash="request-hash",
        result=pending,
    )
    first = asyncio.run(adapter.poll(pending=record))
    assert first.status == "PENDING"
    record = replace(record, result=first)
    completed = asyncio.run(adapter.poll(pending=record))
    assert completed.status == "SUCCEEDED"
    assert completed.output_ref is not None and completed.output_ref.startswith("fixture://mock/video/")


def test_image_to_video_requires_feature_registry_and_routes_to_matching_provider_key() -> None:
    source = _source()
    spec = _spec(mode="IMAGE_TO_VIDEO", source_images=(source,))
    shot = compile_storyboard(spec).shots[0]
    p1 = MockProvider(provider="p1", model="video-a", quality_score=95)
    p2 = MockProvider(provider="p2", model="video-b", quality_score=90)
    gateway = _real_gateway(p1, p2)
    with pytest.raises(ValueError, match="VIDEO_PROVIDER_FEATURE_REGISTRY_REQUIRED"):
        asyncio.run(ModelGatewayVideoAdapter(gateway).submit(spec=spec, shot=shot, continuity_refs=()))
    registry = VideoFeatureRegistry(
        snapshot_id="video-features-v1",
        provider_features={
            "p1:video-a": frozenset(),
            "p2:video-b": frozenset({"video.start_frame"}),
        },
    )
    result = asyncio.run(
        ModelGatewayVideoAdapter(gateway, feature_registry=registry).submit(
            spec=spec,
            shot=shot,
            continuity_refs=(),
        )
    )
    assert result.status == "PENDING"
    assert result.provider == "p2"
    assert "VIDEO_FEATURE_REGISTRY:video-features-v1" in result.routing_reason_codes


class FakeResolver:
    def resolve_readonly(self, durable_ref: str) -> str:
        return "/sandbox/input/clip;not-a-shell-command.mp4" if durable_ref else "/sandbox/input/x.mp4"

    def allocate_output(self, suffix: str) -> str:
        return "/sandbox/output/final" + suffix


class BadResolver(FakeResolver):
    def resolve_readonly(self, durable_ref: str) -> str:
        del durable_ref
        return "/tmp/escape.mp4"


def _timeline(*, transition: str = "CUT") -> VideoTimeline:
    return VideoTimeline(
        clips=(TimelineClip(
            shot_id="s1",
            artifact_version_id="v1",
            durable_ref="asset:clip:v1",
            duration_seconds=Decimal("2"),
        ),),
        overlays=(),
        audio_tracks=(),
        transitions=() if transition == "CUT" else (TimelineTransition(
            from_shot_id="s1",
            to_shot_id="s2",
            kind=transition,  # type: ignore[arg-type]
        ),),
        output_spec=VideoOutputSpec(width=1600, height=900, fps=24),
    )


def test_ffmpeg_compiler_uses_argv_not_shell_and_sandbox_paths() -> None:
    invocation = FfmpegArgvCompiler().compile(_timeline(), FakeResolver())
    assert invocation.argv[0] == "ffmpeg"
    assert "/sandbox/input/clip;not-a-shell-command.mp4" in invocation.argv
    assert invocation.limits.network_disabled is True
    assert invocation.output_path.startswith("/sandbox/")
    with pytest.raises(ValueError, match="VIDEO_SANDBOX_PATH_INVALID"):
        FfmpegArgvCompiler().compile(_timeline(), BadResolver())


def test_ffmpeg_v1_rejects_unimplemented_crossfade_instead_of_guessing() -> None:
    with pytest.raises(ValueError, match="VIDEO_FFMPEG_TRANSITION_NOT_SUPPORTED_V1"):
        FfmpegArgvCompiler().compile(_timeline(transition="CROSSFADE"), FakeResolver())
