from __future__ import annotations

from lumi_domain.performance_events import (
    PerformanceEventSink,
    PerformanceStage,
    PerformanceTelemetryContext,
    measure_performance_stage,
)

from .model import RenderedVideo, VideoTimeline
from .ports import MediaSandboxPort

_SERVICE = "worker-media"


class TimedMediaSandbox:
    """Measure only real FFmpeg/timeline composition as video postprocess."""

    def __init__(
        self,
        inner: MediaSandboxPort,
        telemetry: PerformanceTelemetryContext | None,
        *,
        operation_id: str,
        task_id: str,
        sink: PerformanceEventSink | None = None,
    ) -> None:
        self.inner = inner
        self.telemetry = telemetry
        self.operation_id = operation_id
        self.task_id = task_id
        self.sink = sink

    async def render(self, timeline: VideoTimeline) -> RenderedVideo:
        with measure_performance_stage(
            self.telemetry,
            stage=PerformanceStage.POSTPROCESS,
            service=_SERVICE,
            operation_id=self.operation_id,
            task_id=self.task_id,
            sink=self.sink,
        ):
            return await self.inner.render(timeline)
