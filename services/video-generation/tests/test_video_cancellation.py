from __future__ import annotations

import asyncio
from decimal import Decimal

from lumi_artifacts.history import ArtifactHistory
from lumi_video_generation.artifact_adapter import ArtifactHistoryVideoAdapter
from lumi_video_generation.inmemory import MemoryMediaSandbox, MemoryVideoOutput
from lumi_video_generation.model import (
    CompiledShot,
    GatewayEstimate,
    GatewayVideoResult,
    ProviderJobRecord,
    ShotRuntime,
    ShotSpec,
    StoredVideoClip,
    VideoJob,
    VideoProbeResult,
    VideoTaskSpec,
)
from lumi_video_generation.pipeline import VideoGenerationPipeline
from lumi_video_generation.repository import InMemoryVideoRepository
from lumi_video_generation.validation import CompositeVideoValidator

ORG = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"
VIDEO_JOB_ID = "video-job-cancellation-contract"
OPERATION_ID = "00000000-0000-0000-0000-000000000004"
SHOT_ID = "shot-1"
PAID_OPERATION_ID = "00000000-0000-0000-0000-000000000005"
PROVIDER_REQUEST_ID = "provider-video-1"


def _spec() -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION_ID,
        mode="TEXT_TO_VIDEO",
        prompt="Cancellation provider truth",
        duration_seconds=Decimal("4"),
        aspect_ratio="16:9",
        width=1280,
        height=720,
        fps=24,
        budget_limit_usd=Decimal("5"),
        code_git_sha="d" * 40,
        shots=(
            ShotSpec(
                shot_id=SHOT_ID,
                duration_seconds=Decimal("4"),
                prompt="Cancellation provider truth",
            ),
        ),
        quality_retry_limit=1,
    )


def _result(status: str, *, cost: str = "0.25") -> GatewayVideoResult:
    return GatewayVideoResult(
        status=status,  # type: ignore[arg-type]
        provider="provider-a",
        model="video-a",
        provider_request_id=PROVIDER_REQUEST_ID,
        output_ref="provider-output" if status == "SUCCEEDED" else None,
        output_mime_type="video/mp4" if status == "SUCCEEDED" else None,
        cost_usd=Decimal(cost),
        cost_confidence="EXACT",
        pricing_snapshot_id="price-v1",
        routing_reason_codes=("CANCEL_RECONCILIATION",),
    )


def _clip() -> tuple[StoredVideoClip, VideoProbeResult]:
    keyframes = ("asset:keyframe:cancel-success:0", "asset:keyframe:cancel-success:1")
    clip = StoredVideoClip(
        storage_key="video/clips/cancel-success.mp4",
        checksum_sha256="e" * 64,
        mime_type="video/mp4",
        size_bytes=4096,
        width=1280,
        height=720,
        duration_ms=4000,
        durable_asset_ref="asset:video-clip:cancel-success",
        poster_frame_ref="asset:poster:cancel-success",
        tail_frame_ref="asset:tail:cancel-success",
        keyframe_refs=keyframes,
    )
    probe = VideoProbeResult(
        decode_ok=True,
        mime_type="video/mp4",
        container="mp4",
        video_codec="h264",
        width=1280,
        height=720,
        fps=Decimal("24"),
        duration_seconds=Decimal("4"),
        keyframe_refs=keyframes,
        poster_frame_ref=clip.poster_frame_ref,
        tail_frame_ref=clip.tail_frame_ref,
    )
    return clip, probe


def _job(spec: VideoTaskSpec) -> VideoJob:
    return VideoJob(
        video_job_id=VIDEO_JOB_ID,
        organization_id=ORG,
        operation_id=OPERATION_ID,
        semantic_hash=spec.semantic_hash,
        storyboard_hash="b" * 64,
        status="WAITING_EXTERNAL",
        shots=(
            ShotRuntime(
                shot_id=SHOT_ID,
                ordinal=1,
                paid_operation_id=PAID_OPERATION_ID,
                status="WAITING_EXTERNAL",
                attempt_count=0,
                provider="provider-a",
                model="video-a",
                provider_request_id=PROVIDER_REQUEST_ID,
            ),
        ),
        estimated_cost_usd=Decimal("0.25"),
    )


def _provider_record(result: GatewayVideoResult | None = None) -> ProviderJobRecord:
    return ProviderJobRecord(
        organization_id=ORG,
        video_job_id=VIDEO_JOB_ID,
        shot_id=SHOT_ID,
        paid_operation_id=PAID_OPERATION_ID,
        request_hash="c" * 64,
        result=result or _result("PENDING"),
    )


class _Gateway:
    def __init__(self, result: GatewayVideoResult) -> None:
        self.result = result
        self.cancel_count = 0
        self.estimate_count = 0
        self.submit_count = 0

    async def estimate(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        continuity_refs: tuple[str, ...],
        excluded_provider_keys: tuple[str, ...] = (),
    ) -> GatewayEstimate:
        del spec, shot, continuity_refs, excluded_provider_keys
        self.estimate_count += 1
        return GatewayEstimate(
            amount_usd=Decimal("0.25"),
            provider="provider-b",
            model="video-b",
            pricing_snapshot_id="price-v2",
            routing_reason_codes=("QUALITY_RETRY",),
        )

    async def submit(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        continuity_refs: tuple[str, ...],
        excluded_provider_keys: tuple[str, ...] = (),
    ) -> GatewayVideoResult:
        del spec, shot, continuity_refs, excluded_provider_keys
        self.submit_count += 1
        return GatewayVideoResult(
            status="PENDING",
            provider="provider-b",
            model="video-b",
            provider_request_id="provider-video-retry",
            output_ref=None,
            output_mime_type=None,
            cost_usd=Decimal("0.25"),
            cost_confidence="EXACT",
            pricing_snapshot_id="price-v2",
            routing_reason_codes=("QUALITY_RETRY",),
        )

    async def cancel(self, *, pending: ProviderJobRecord) -> GatewayVideoResult:
        assert pending.result.provider_request_id == PROVIDER_REQUEST_ID
        self.cancel_count += 1
        return self.result


class _Costs:
    def __init__(self) -> None:
        self.calls = 0

    async def record_terminal(self, **kwargs: object) -> bool:
        del kwargs
        self.calls += 1
        return True


class _Events:
    def __init__(self) -> None:
        self.types: list[str] = []

    async def emit(
        self,
        event_type: str,
        *,
        organization_id: str,
        video_job_id: str,
        payload: object,
    ) -> None:
        del organization_id, video_job_id, payload
        self.types.append(event_type)


def _pipeline(
    cancel_result: GatewayVideoResult,
    *,
    include_provider_record: bool = True,
    outputs: dict[str, tuple[StoredVideoClip, VideoProbeResult]] | None = None,
) -> tuple[VideoGenerationPipeline, InMemoryVideoRepository, _Gateway, _Costs, _Events]:
    repository = InMemoryVideoRepository()
    spec = _spec()
    repository.save_spec(spec)
    repository.save(_job(spec))
    if include_provider_record:
        repository.save_provider_job(_provider_record())
    gateway = _Gateway(cancel_result)
    costs = _Costs()
    events = _Events()
    pipeline = VideoGenerationPipeline(
        repository=repository,
        gateway=gateway,  # type: ignore[arg-type]
        output=MemoryVideoOutput(outputs or {}),
        validator=CompositeVideoValidator(),
        artifacts=ArtifactHistoryVideoAdapter(ArtifactHistory()),
        sandbox=MemoryMediaSandbox(),
        costs=costs,  # type: ignore[arg-type]
        events=events,  # type: ignore[arg-type]
    )
    return pipeline, repository, gateway, costs, events


def _cancel(pipeline: VideoGenerationPipeline) -> VideoJob:
    return asyncio.run(pipeline.cancel(organization_id=ORG, video_job_id=VIDEO_JOB_ID))


def test_pending_cancel_result_preserves_provider_job_and_waiting_state() -> None:
    pipeline, repository, gateway, costs, events = _pipeline(_result("PENDING"))

    job = _cancel(pipeline)

    assert job.status == "WAITING_EXTERNAL"
    assert gateway.cancel_count == 1
    assert costs.calls == 0
    assert "video_generation.cancelled" not in events.types
    pending = repository.get_provider_job(ORG, VIDEO_JOB_ID, SHOT_ID, PAID_OPERATION_ID)
    assert pending is not None
    assert pending.result.status == "PENDING"
    assert repository.provider_jobs


def test_terminal_non_cancel_result_is_preserved_for_resume_truth() -> None:
    for status in ("SUCCEEDED", "FAILED"):
        pipeline, repository, _, costs, events = _pipeline(_result(status))

        job = _cancel(pipeline)

        assert job.status == "WAITING_EXTERNAL"
        assert costs.calls == 0
        assert "video_generation.cancelled" not in events.types
        pending = repository.get_provider_job(ORG, VIDEO_JOB_ID, SHOT_ID, PAID_OPERATION_ID)
        assert pending is not None
        assert pending.result.status == status
        assert repository.provider_jobs


def test_cancelled_result_is_only_provider_result_that_marks_job_cancelled() -> None:
    pipeline, repository, gateway, costs, events = _pipeline(_result("CANCELLED"))

    job = _cancel(pipeline)

    assert job.status == "CANCELLED"
    assert all(shot.status == "CANCELLED" for shot in job.shots)
    assert gateway.cancel_count == 1
    assert costs.calls == 1
    assert events.types.count("video_generation.cancelled") == 1
    assert not repository.provider_jobs
    archived = repository.get_provider_job(ORG, VIDEO_JOB_ID, SHOT_ID, PAID_OPERATION_ID)
    assert archived is not None
    assert archived.result.status == "CANCELLED"


def test_missing_provider_recovery_never_self_certifies_cancellation() -> None:
    pipeline, repository, gateway, costs, events = _pipeline(
        _result("CANCELLED"),
        include_provider_record=False,
    )

    job = _cancel(pipeline)

    assert job.status == "WAITING_EXTERNAL"
    assert gateway.cancel_count == 0
    assert costs.calls == 0
    assert "video_generation.cancelled" not in events.types
    assert repository.get_provider_job(ORG, VIDEO_JOB_ID, SHOT_ID, PAID_OPERATION_ID) is None


def test_cancellation_terminal_reconciliation_never_launches_quality_retry() -> None:
    pipeline, repository, gateway, costs, events = _pipeline(_result("FAILED"))

    cancelled_attempt = _cancel(pipeline)
    assert cancelled_attempt.status == "WAITING_EXTERNAL"

    reconciled = asyncio.run(
        pipeline.resume(
            organization_id=ORG,
            video_job_id=VIDEO_JOB_ID,
            allow_quality_retry=False,
        )
    )

    assert reconciled.status == "FAILED"
    assert reconciled.error_code == "VIDEO_PROVIDER_FAILED"
    assert gateway.estimate_count == 0
    assert gateway.submit_count == 0
    assert costs.calls == 1
    assert "video_generation.shot_quality_retry" not in events.types
    archived = repository.get_provider_job(ORG, VIDEO_JOB_ID, SHOT_ID, PAID_OPERATION_ID)
    assert archived is not None
    assert archived.result.status == "FAILED"


def test_successful_provider_truth_wins_over_cancellation_intent() -> None:
    pipeline, repository, gateway, costs, events = _pipeline(
        _result("SUCCEEDED"),
        outputs={"provider-output": _clip()},
    )

    cancelled_attempt = _cancel(pipeline)
    assert cancelled_attempt.status == "WAITING_EXTERNAL"

    reconciled = asyncio.run(
        pipeline.resume(
            organization_id=ORG,
            video_job_id=VIDEO_JOB_ID,
            allow_quality_retry=False,
        )
    )

    assert reconciled.status == "COMPLETED"
    assert reconciled.final_artifact_version_id is not None
    assert gateway.estimate_count == 0
    assert gateway.submit_count == 0
    assert costs.calls == 1
    assert "video_generation.cancelled" not in events.types
    assert events.types.count("video_generation.completed") == 1
    archived = repository.get_provider_job(ORG, VIDEO_JOB_ID, SHOT_ID, PAID_OPERATION_ID)
    assert archived is not None
    assert archived.result.status == "SUCCEEDED"
