from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from lumi_domain.performance_events import (
    PerformanceOutcome,
    PerformanceStage,
    PerformanceStageEvent,
    PerformanceTelemetryContext,
)

from lumi_video_generation.model import (
    RenderedVideo,
    StoredVideoClip,
    TimelineClip,
    VideoOutputSpec,
    VideoTimeline,
)
from lumi_video_generation.performance_ports import TimedMediaSandbox


class RecordingSandbox:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def render(self, timeline: VideoTimeline) -> RenderedVideo:
        self.calls += 1
        assert timeline.clips[0].shot_id == "shot-1"
        if self.error is not None:
            raise self.error
        clip = StoredVideoClip(
            storage_key="video/final/rendered.mp4",
            checksum_sha256="a" * 64,
            mime_type="video/mp4",
            size_bytes=1024,
            width=1600,
            height=900,
            duration_ms=2000,
            durable_asset_ref="asset:video-final",
            poster_frame_ref=None,
            tail_frame_ref=None,
            keyframe_refs=(),
        )
        return RenderedVideo(video=clip)


def _timeline() -> VideoTimeline:
    return VideoTimeline(
        clips=(
            TimelineClip(
                shot_id="shot-1",
                artifact_version_id="artifact-version-1",
                durable_ref="asset:video-clip:1",
                duration_seconds=Decimal("2"),
            ),
        ),
        overlays=(),
        audio_tracks=(),
        transitions=(),
        output_spec=VideoOutputSpec(width=1600, height=900, fps=24),
    )


def _telemetry() -> PerformanceTelemetryContext:
    return PerformanceTelemetryContext(
        performance_run_id="node69-video-postprocess",
        profile_id="D",
        source_rc_sha="b" * 40,
    )


def test_timed_media_sandbox_records_real_postprocess() -> None:
    events: list[PerformanceStageEvent] = []
    inner = RecordingSandbox()
    timed = TimedMediaSandbox(
        inner,
        _telemetry(),
        operation_id="operation-video-1",
        task_id="task-video-1",
        sink=events.append,
    )

    rendered = asyncio.run(timed.render(_timeline()))

    assert rendered.video.storage_key == "video/final/rendered.mp4"
    assert inner.calls == 1
    assert len(events) == 1
    event = events[0]
    assert event.stage == PerformanceStage.POSTPROCESS
    assert event.outcome == PerformanceOutcome.SUCCESS
    assert event.operation_id == "operation-video-1"
    assert event.task_id == "task-video-1"
    assert event.service == "worker-media"
    assert event.duration_ms >= 0


def test_timed_media_sandbox_records_error_and_preserves_exception() -> None:
    events: list[PerformanceStageEvent] = []
    inner = RecordingSandbox(error=RuntimeError("ffmpeg failed"))
    timed = TimedMediaSandbox(
        inner,
        _telemetry(),
        operation_id="operation-video-2",
        task_id="task-video-2",
        sink=events.append,
    )

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        asyncio.run(timed.render(_timeline()))

    assert inner.calls == 1
    assert len(events) == 1
    assert events[0].stage == PerformanceStage.POSTPROCESS
    assert events[0].outcome == PerformanceOutcome.ERROR
    assert events[0].task_id == "task-video-2"


def test_timed_media_sandbox_is_noop_when_telemetry_disabled() -> None:
    events: list[PerformanceStageEvent] = []
    inner = RecordingSandbox()
    timed = TimedMediaSandbox(
        inner,
        None,
        operation_id="operation-video-3",
        task_id="task-video-3",
        sink=events.append,
    )

    asyncio.run(timed.render(_timeline()))

    assert inner.calls == 1
    assert events == []
