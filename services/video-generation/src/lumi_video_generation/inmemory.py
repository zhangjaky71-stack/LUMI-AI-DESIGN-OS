from __future__ import annotations

import hashlib
from collections import deque
from decimal import Decimal
from typing import Mapping

from .model import CompiledShot, GatewayEstimate, GatewayVideoResult, ProviderJobRecord, RenderedVideo, StoredVideoClip, VideoProbeResult, VideoTaskSpec, VideoTimeline


class ScriptedVideoGateway:
    def __init__(self, *, estimate: GatewayEstimate, submits: tuple[GatewayVideoResult, ...], polls: tuple[GatewayVideoResult, ...] = ()) -> None:
        self.estimate_result = estimate
        self.submits = deque(submits)
        self.polls = deque(polls)
        self.submit_count = 0
        self.poll_count = 0
        self.cancel_count = 0

    async def estimate(self, *, spec: VideoTaskSpec, shot: CompiledShot, continuity_refs: tuple[str, ...]) -> GatewayEstimate:
        del spec, shot, continuity_refs
        return self.estimate_result

    async def submit(self, *, spec: VideoTaskSpec, shot: CompiledShot, continuity_refs: tuple[str, ...]) -> GatewayVideoResult:
        del spec, shot, continuity_refs
        self.submit_count += 1
        return self.submits.popleft()

    async def poll(self, *, pending: ProviderJobRecord) -> GatewayVideoResult:
        del pending
        self.poll_count += 1
        return self.polls.popleft()

    async def cancel(self, *, pending: ProviderJobRecord) -> GatewayVideoResult:
        self.cancel_count += 1
        return GatewayVideoResult(
            status="CANCELLED",
            provider=pending.result.provider,
            model=pending.result.model,
            provider_request_id=pending.result.provider_request_id,
            output_ref=None,
            output_mime_type=None,
            cost_usd=Decimal("0"),
            cost_confidence="EXACT",
            pricing_snapshot_id="fixture-price",
            routing_reason_codes=("CANCELLED",),
        )


class MemoryVideoOutput:
    def __init__(self, fixtures: Mapping[str, tuple[StoredVideoClip, VideoProbeResult]]) -> None:
        self.fixtures = dict(fixtures)

    async def materialize_and_probe(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        output_ref: str,
        declared_mime_type: str | None,
    ) -> tuple[StoredVideoClip, VideoProbeResult]:
        del spec, shot
        clip, probe = self.fixtures[output_ref]
        if declared_mime_type is not None and declared_mime_type != probe.mime_type:
            raise ValueError("VIDEO_DECLARED_MIME_MISMATCH")
        return clip, probe


class MemoryVideoCostLedger:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, object]] = {}

    async def record_terminal(
        self,
        *,
        video_job_id: str,
        shot_id: str,
        paid_operation_id: str,
        provider: str,
        model: str,
        provider_request_id: str | None,
        amount_usd: Decimal | None,
        confidence: str,
        pricing_snapshot_id: str | None,
    ) -> bool:
        if paid_operation_id in self.records:
            return False
        self.records[paid_operation_id] = {
            "video_job_id": video_job_id,
            "shot_id": shot_id,
            "provider": provider,
            "model": model,
            "provider_request_id": provider_request_id,
            "amount_usd": amount_usd,
            "confidence": confidence,
            "pricing_snapshot_id": pricing_snapshot_id,
        }
        return True


class MemoryVideoEvents:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str, dict[str, object]]] = []

    async def emit(self, event_type: str, *, organization_id: str, video_job_id: str, payload: Mapping[str, object]) -> None:
        self.events.append((event_type, organization_id, video_job_id, dict(payload)))


class MemoryMediaSandbox:
    def __init__(self) -> None:
        self.render_count = 0
        self.last_timeline: VideoTimeline | None = None

    async def render(self, timeline: VideoTimeline) -> RenderedVideo:
        self.render_count += 1
        self.last_timeline = timeline
        duration = sum((item.duration_seconds for item in timeline.clips), Decimal("0"))
        digest = hashlib.sha256(":".join(item.artifact_version_id for item in timeline.clips).encode()).hexdigest()
        video = StoredVideoClip(
            storage_key=f"video/final/{digest}.mp4",
            checksum_sha256=digest,
            mime_type="video/mp4",
            size_bytes=1024,
            width=timeline.output_spec.width,
            height=timeline.output_spec.height,
            duration_ms=int(duration * Decimal("1000")),
            durable_asset_ref=f"asset:video-final:{digest}",
            poster_frame_ref=f"asset:video-poster:{digest}",
            tail_frame_ref=f"asset:video-tail:{digest}",
            keyframe_refs=(f"asset:video-keyframe:{digest}:0",),
        )
        thumb_hash = hashlib.sha256((digest + ":thumb").encode()).hexdigest()
        return RenderedVideo(
            video=video,
            thumbnail_storage_key=f"video/final/{digest}.jpg",
            thumbnail_checksum_sha256=thumb_hash,
        )
