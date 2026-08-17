from __future__ import annotations

import asyncio
from decimal import Decimal

from lumi_video_generation.model import (
    GatewayEstimate,
    GatewayVideoResult,
    ShotSpec,
    VideoJobStatus,
    VideoMode,
    VideoTaskSpec,
)
from lumi_video_generation.pipeline import VideoGenerationPipeline
from lumi_video_generation.repository import InMemoryVideoRepository


class CancelledProviderGateway:
    async def estimate(self, *, spec, shot, excluded_provider_keys=()):
        return GatewayEstimate(
            amount_usd=Decimal("0.1"),
            provider="mock",
            model="video-v1",
            pricing_snapshot_id="price-v1",
        )

    async def submit(self, *, spec, shot, excluded_provider_keys=()):
        return GatewayVideoResult(
            status="PENDING",
            provider="mock",
            model="video-v1",
            provider_request_id="provider-job-1",
        )

    async def poll(self, *, pending):
        return GatewayVideoResult(
            status="CANCELLED",
            provider=pending.result.provider,
            model=pending.result.model,
            provider_request_id=pending.result.provider_request_id,
        )

    async def cancel(self, *, pending):
        return True


class UnusedPort:
    async def materialize_and_validate(self, **kwargs):
        raise AssertionError("output must not run")

    async def validate(self, **kwargs):
        raise AssertionError("validation must not run")

    async def render(self, **kwargs):
        raise AssertionError("renderer must not run")

    async def append_clip(self, **kwargs):
        raise AssertionError("artifact append must not run")

    async def append_final(self, **kwargs):
        raise AssertionError("artifact append must not run")


def _spec() -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id="org-1",
        project_id="project-1",
        task_id="task-1",
        operation_id="operation-1",
        mode=VideoMode.TEXT_TO_VIDEO,
        width=1280,
        height=720,
        fps=30,
        shots=(
            ShotSpec(
                shot_id="shot-1",
                duration_seconds=Decimal("4"),
                prompt="hero motion",
            ),
        ),
    )


def test_unexpected_provider_cancellation_fails_job_and_failed_cancel_is_noop():
    async def scenario():
        repository = InMemoryVideoRepository()
        unused = UnusedPort()
        pipeline = VideoGenerationPipeline(
            repository=repository,
            gateway=CancelledProviderGateway(),
            output=unused,
            validator=unused,
            renderer=unused,
            artifacts=unused,
        )
        waiting = await pipeline.start(_spec())
        assert waiting.status is VideoJobStatus.WAITING_EXTERNAL

        failed = await pipeline.resume(waiting.job_id)
        assert failed.status is VideoJobStatus.FAILED
        assert failed.shots[0].error_code == "VIDEO_PROVIDER_CANCELLED_UNEXPECTEDLY"

        unchanged = await pipeline.cancel(waiting.job_id)
        assert unchanged.status is VideoJobStatus.FAILED
        assert unchanged.shots[0].error_code == "VIDEO_PROVIDER_CANCELLED_UNEXPECTEDLY"

    asyncio.run(scenario())
