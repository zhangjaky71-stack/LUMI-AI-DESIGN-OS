from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from lumi_video_generation.model import (
    DurableVideoObject,
    GatewayEstimate,
    GatewayVideoResult,
    RenderedVideo,
    ShotSpec,
    ShotValidationReport,
    SourceImageRef,
    StoredVideoClip,
    ValidationDecision,
    VideoJobStatus,
    VideoMode,
    VideoProbeResult,
    VideoTaskSpec,
)
from lumi_video_generation.pipeline import VideoGenerationPipeline
from lumi_video_generation.repository import (
    InMemoryVideoRepository,
    VideoOperationConflict,
)
from lumi_video_generation.storyboard import (
    compile_storyboard,
    retry_shot_operation_id,
)


class FakeGateway:
    def __init__(self) -> None:
        self.poll_status: dict[str, str] = {}
        self.poll_errors: set[str] = set()
        self.cancel_accept = True
        self.submits: list[tuple[str, tuple[str, ...]]] = []

    async def estimate(self, *, spec, shot, excluded_provider_keys=()):
        return GatewayEstimate(
            Decimal("0.10"),
            "mock",
            "video-v1",
            "price-v1",
        )

    async def submit(self, *, spec, shot, excluded_provider_keys=()):
        self.submits.append((shot.shot.shot_id, excluded_provider_keys))
        provider = "mock-retry" if excluded_provider_keys else "mock"
        request_id = f"req:{shot.shot.shot_id}:{shot.retry_ordinal}"
        return GatewayVideoResult(
            status="PENDING",
            provider=provider,
            model="video-v1",
            provider_request_id=request_id,
        )

    async def poll(self, *, pending):
        request_id = pending.result.provider_request_id or ""
        if request_id in self.poll_errors:
            self.poll_errors.remove(request_id)
            raise TimeoutError("transient")
        status = self.poll_status.get(request_id, "COMPLETED")
        return GatewayVideoResult(
            status=status,
            provider=pending.result.provider,
            model=pending.result.model,
            provider_request_id=pending.result.provider_request_id,
            output_ref=(
                f"provider://{pending.shot_id}"
                if status == "COMPLETED"
                else None
            ),
            cost_usd=(
                Decimal("0.08") if status == "COMPLETED" else None
            ),
        )

    async def cancel(self, *, pending):
        return self.cancel_accept


class FakeOutput:
    def __init__(self) -> None:
        self.calls = 0

    async def materialize_and_validate(self, *, spec, shot, result):
        self.calls += 1
        shot_id = shot.shot.shot_id
        return StoredVideoClip(
            shot_id=shot_id,
            object=DurableVideoObject(
                durable_ref=f"asset:video:{shot_id}:{shot.retry_ordinal}",
                bucket="generated-video",
                storage_key=f"video/{shot_id}/{shot.retry_ordinal}.mp4",
                size_bytes=1024,
            ),
            checksum_sha256="a" * 64,
            probe=VideoProbeResult(
                mime_type="video/mp4",
                width=spec.width,
                height=spec.height,
                duration_seconds=shot.shot.duration_seconds,
                decodable_frames=120,
            ),
            provider=result.provider,
            model=result.model,
            provider_request_id=result.provider_request_id or "missing",
        )


class FakeValidator:
    async def validate(self, *, spec, shot, clip, provider_result):
        return ShotValidationReport(
            ValidationDecision.PASS,
            (),
            True,
            True,
        )


class FakeRenderer:
    async def render(self, *, timeline):
        duration = sum(
            (clip.duration_seconds for clip in timeline.clips),
            Decimal("0"),
        )
        return RenderedVideo(
            object=DurableVideoObject(
                durable_ref="asset:video:final",
                bucket="generated-video",
                storage_key="video/final.mp4",
                size_bytes=4096,
            ),
            checksum_sha256="b" * 64,
            probe=VideoProbeResult(
                mime_type="video/mp4",
                width=timeline.width,
                height=timeline.height,
                duration_seconds=duration,
                decodable_frames=240,
            ),
            renderer_version="ffmpeg-7.1",
        )


class FakeArtifacts:
    def __init__(self) -> None:
        self.clip_count = 0
        self.final_count = 0

    async def append_clip(self, *, job, clip):
        self.clip_count += 1
        return f"artifact-version:{clip.shot_id}"

    async def append_final(self, *, job, video):
        self.final_count += 1
        return "artifact-version:final"


def make_spec(
    *,
    operation_id: str = "op-1",
    shots: int = 2,
) -> VideoTaskSpec:
    source = SourceImageRef(
        asset_id="asset-1",
        asset_version="v1",
        durable_ref="asset:source:v1",
        checksum_sha256="c" * 64,
        rights_snapshot_id="rights-v1",
    )
    items = []
    for index in range(shots):
        items.append(
            ShotSpec(
                shot_id=f"shot-{index + 1}",
                duration_seconds=Decimal("4"),
                prompt=f"Product hero shot {index + 1}",
                source_ref=source if index == 0 else None,
                identity_refs=("identity-product",),
            )
        )
    return VideoTaskSpec(
        organization_id="org-1",
        project_id="project-1",
        task_id="task-1",
        operation_id=operation_id,
        mode=VideoMode.PRODUCT_MOTION,
        width=1280,
        height=720,
        fps=30,
        shots=tuple(items),
        budget_limit_usd=Decimal("1.00"),
        brand_rule_snapshot_id="brand-v3",
        agent_run_id="run-1",
        agent_id="video-agent",
        recipe_id="campaign-video-v1",
        skill_refs=("storyboard@1", "video-quality@1"),
        git_commit="d" * 40,
    )


def make_pipeline(gateway=None):
    gateway = gateway or FakeGateway()
    repo = InMemoryVideoRepository()
    output = FakeOutput()
    artifacts = FakeArtifacts()
    pipeline = VideoGenerationPipeline(
        repository=repo,
        gateway=gateway,
        output=output,
        validator=FakeValidator(),
        renderer=FakeRenderer(),
        artifacts=artifacts,
    )
    return pipeline, repo, gateway, output, artifacts


def test_storyboard_operation_ids_are_deterministic_and_retry_is_distinct():
    spec = make_spec(shots=1)
    first = compile_storyboard(spec)[0]
    again = compile_storyboard(spec)[0]
    retry = retry_shot_operation_id(
        spec.operation_id,
        first.shot.shot_id,
        1,
    )
    assert first.paid_operation_id == again.paid_operation_id
    assert retry != first.paid_operation_id


def test_storyboard_to_final_video_and_provenance():
    async def scenario():
        pipeline, _, _, _, artifacts = make_pipeline()
        job = await pipeline.start(make_spec())
        assert job.status is VideoJobStatus.WAITING_EXTERNAL
        completed = await pipeline.resume(job.job_id)
        assert completed.status is VideoJobStatus.COMPLETED
        assert completed.final_video is not None
        assert completed.provenance is not None
        assert len(completed.provenance.source_shots) == 2
        assert completed.provenance.git_commit == "d" * 40
        assert completed.final_artifact_version_id == "artifact-version:final"
        assert all(
            item.artifact_version_id is not None
            for item in completed.shots
        )
        assert artifacts.clip_count == 2
        assert artifacts.final_count == 1

    asyncio.run(scenario())


def test_failed_shot_can_retry_without_regenerating_ready_shot():
    async def scenario():
        gateway = FakeGateway()
        gateway.poll_status["req:shot-2:0"] = "FAILED"
        pipeline, _, _, output, _ = make_pipeline(gateway)
        job = await pipeline.start(make_spec())
        failed = await pipeline.resume(job.job_id)
        assert failed.status is VideoJobStatus.FAILED
        assert output.calls == 1
        gateway.poll_status["req:shot-2:1"] = "COMPLETED"
        retried = await pipeline.retry_shot(job.job_id, "shot-2")
        assert retried.status is VideoJobStatus.WAITING_EXTERNAL
        completed = await pipeline.resume(job.job_id)
        assert completed.status is VideoJobStatus.COMPLETED
        assert output.calls == 2
        assert gateway.submits[-1][1] == ("mock",)

    asyncio.run(scenario())


def test_transient_poll_error_keeps_job_resumable():
    async def scenario():
        gateway = FakeGateway()
        gateway.poll_errors.add("req:shot-1:0")
        pipeline, _, _, output, _ = make_pipeline(gateway)
        job = await pipeline.start(make_spec(shots=1))
        waiting = await pipeline.resume(job.job_id)
        assert waiting.status is VideoJobStatus.WAITING_EXTERNAL
        assert output.calls == 0
        completed = await pipeline.resume(job.job_id)
        assert completed.status is VideoJobStatus.COMPLETED
        assert output.calls == 1

    asyncio.run(scenario())


def test_cancel_request_discards_late_provider_completion():
    async def scenario():
        gateway = FakeGateway()
        gateway.cancel_accept = False
        pipeline, _, _, output, _ = make_pipeline(gateway)
        job = await pipeline.start(make_spec(shots=1))
        cancelling = await pipeline.cancel(job.job_id)
        assert cancelling.status is VideoJobStatus.CANCEL_REQUESTED
        cancelled = await pipeline.resume(job.job_id)
        assert cancelled.status is VideoJobStatus.CANCELLED
        assert output.calls == 0

    asyncio.run(scenario())


def test_operation_id_is_idempotent_but_semantic_reuse_conflicts():
    async def scenario():
        pipeline, _, _, _, _ = make_pipeline()
        first = await pipeline.start(
            make_spec(operation_id="same-op", shots=1)
        )
        same = await pipeline.start(
            make_spec(operation_id="same-op", shots=1)
        )
        assert first.job_id == same.job_id
        changed = make_spec(operation_id="same-op", shots=2)
        with pytest.raises(VideoOperationConflict):
            await pipeline.start(changed)

    asyncio.run(scenario())


def test_webhook_dedupe_claim_is_deterministic_and_tenant_scoped():
    repo = InMemoryVideoRepository()
    assert repo.claim_webhook("org-a", "mock", "event-1") is True
    assert repo.claim_webhook("org-a", "mock", "event-1") is False
    assert repo.claim_webhook("org-b", "mock", "event-1") is True
