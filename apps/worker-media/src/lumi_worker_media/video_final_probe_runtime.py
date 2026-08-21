from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from decimal import Decimal

from lumi_video_generation.model import RenderedVideo, VideoProbeResult, VideoTaskSpec, VideoTimeline

from .video_generation_ports import (
    HostedVideoMediaSandbox,
    HostedVideoOutputAdapter,
    _decode_ffprobe,
    _head_sha256,
    _sandbox_request,
)

_MAX_FINAL_VIDEO_BYTES = 8 * 1024 * 1024 * 1024
_ALLOWED_MP4_CONTAINERS = frozenset({"mp4", "mov,mp4,m4a,3gp,3g2,mj2"})


class HostedVerifiedVideoMediaSandbox:
    """Render, then independently probe the promoted durable final MP4.

    SandboxExchangeMediaRuntime intentionally records the expected timeline geometry
    when it promotes an ffmpeg output. That expected metadata is not acceptance
    evidence. This wrapper copies the durable object back into the isolated exchange,
    runs ffprobe with network disabled, and replaces the expected metadata with values
    observed from the actual final file before NODE-48 final validation/artifact ready.
    """

    def __init__(
        self,
        *,
        spec: VideoTaskSpec,
        renderer: HostedVideoMediaSandbox,
        probe_adapter: HostedVideoOutputAdapter,
    ) -> None:
        self.spec = spec
        self.renderer = renderer
        self.probe_adapter = probe_adapter

    async def render(self, timeline: VideoTimeline) -> RenderedVideo:
        rendered = await self.renderer.render(timeline)
        probe = await self._probe_durable(rendered)
        return _verified_final_render(rendered, timeline, probe)

    async def _probe_durable(self, rendered: RenderedVideo) -> VideoProbeResult:
        video = rendered.video
        if video.storage_key != video.durable_asset_ref:
            raise RuntimeError("VIDEO_FINAL_DURABLE_REF_MISMATCH")
        prefix = (
            f"generated/video/v1/{self.spec.organization_id}/"
            f"{self.spec.project_id}/"
        )
        key = video.storage_key
        if (
            not key.startswith(prefix)
            or len(key) > 1024
            or "\x00" in key
            or "\n" in key
            or "\r" in key
            or "//" in key
            or "/../" in key
            or key.endswith("/..")
            or not key.endswith(".mp4")
        ):
            raise RuntimeError("VIDEO_FINAL_DURABLE_KEY_INVALID")

        adapter = self.probe_adapter
        source = await adapter.object_store.head(bucket=adapter.bucket, object_key=key)
        if source.content_length <= 0 or source.content_length > _MAX_FINAL_VIDEO_BYTES:
            raise RuntimeError("VIDEO_FINAL_SIZE_INVALID")
        if source.content_type != "video/mp4":
            raise RuntimeError("VIDEO_FINAL_MIME_INVALID")
        checksum = _head_sha256(source.checksum_sha256_b64, source.metadata)
        if source.content_length != video.size_bytes or checksum != video.checksum_sha256:
            raise RuntimeError("VIDEO_FINAL_DURABLE_IDENTITY_MISMATCH")

        scope = hashlib.sha256(
            f"{self.spec.task_id}\x00final-probe\x00{key}".encode("utf-8")
        ).hexdigest()
        exchange_key = (
            f"sandbox-exchange/v1/{self.spec.organization_id}/{scope}/"
            f"final-probe/{checksum}.mp4"
        )
        await adapter.object_store.copy(
            source_bucket=adapter.bucket,
            source_key=key,
            destination_bucket=adapter.exchange_bucket,
            destination_key=exchange_key,
        )
        try:
            staged = await adapter.object_store.head(
                bucket=adapter.exchange_bucket,
                object_key=exchange_key,
            )
            staged_checksum = _head_sha256(
                staged.checksum_sha256_b64,
                staged.metadata,
            )
            if staged.content_length != source.content_length or staged_checksum != checksum:
                raise RuntimeError("VIDEO_FINAL_PROBE_STAGE_IDENTITY_MISMATCH")
            if staged.content_type != "video/mp4":
                raise RuntimeError("VIDEO_FINAL_PROBE_STAGE_MIME_INVALID")

            payload = {
                "organization_id": self.spec.organization_id,
                "agent_run_id": self.spec.task_id,
                "command": [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=format_name,duration:stream=codec_type,codec_name,width,height,r_frame_rate",
                    "-of",
                    "json",
                    "/sandbox/input/final.mp4",
                ],
                "timeout_seconds": 120,
                "exchange_inputs": [
                    {
                        "exchange_key": exchange_key,
                        "path": "input/final.mp4",
                        "max_bytes": source.content_length,
                        "expected_sha256": checksum,
                    }
                ],
                "exchange_outputs": [],
            }
            response = await asyncio.to_thread(
                _sandbox_request,
                base_url=adapter.sandbox_base_url,
                auth_secret=adapter.sandbox_auth_secret,
                timeout_seconds=adapter.sandbox_timeout_seconds,
                payload=payload,
            )
            if response.get("exit_code") != 0:
                raise RuntimeError("VIDEO_FINAL_FFPROBE_FAILED")
            stdout = response.get("stdout")
            if not isinstance(stdout, str) or len(stdout) > 1024 * 1024:
                raise RuntimeError("VIDEO_FINAL_FFPROBE_OUTPUT_INVALID")
            return _decode_ffprobe(stdout)
        finally:
            try:
                await adapter.object_store.delete_candidate(
                    bucket=adapter.exchange_bucket,
                    object_key=exchange_key,
                )
            except Exception:
                pass


def _verified_final_render(
    rendered: RenderedVideo,
    timeline: VideoTimeline,
    probe: VideoProbeResult,
) -> RenderedVideo:
    if not probe.decode_ok:
        raise RuntimeError("VIDEO_FINAL_NOT_DECODABLE")
    if probe.mime_type != "video/mp4":
        raise RuntimeError("VIDEO_FINAL_MIME_INVALID")
    if probe.container.casefold() not in _ALLOWED_MP4_CONTAINERS:
        raise RuntimeError("VIDEO_FINAL_CONTAINER_UNSUPPORTED")
    if probe.video_codec.casefold() != "h264":
        raise RuntimeError("VIDEO_FINAL_CODEC_MISMATCH")

    output = timeline.output_spec
    if probe.width != output.width or probe.height != output.height:
        raise RuntimeError("VIDEO_FINAL_RESOLUTION_MISMATCH")
    if abs(probe.fps - Decimal(output.fps)) > Decimal("0.01"):
        raise RuntimeError("VIDEO_FINAL_FPS_MISMATCH")

    expected_seconds = sum(
        (clip.duration_seconds for clip in timeline.clips),
        Decimal("0"),
    )
    if abs(probe.duration_seconds - expected_seconds) > Decimal("0.25"):
        raise RuntimeError("VIDEO_FINAL_DURATION_MISMATCH")
    if bool(timeline.audio_tracks) != probe.has_audio:
        raise RuntimeError(
            "VIDEO_FINAL_AUDIO_MISSING" if timeline.audio_tracks else "VIDEO_FINAL_UNEXPECTED_AUDIO"
        )

    verified_video = replace(
        rendered.video,
        mime_type="video/mp4",
        width=probe.width,
        height=probe.height,
        duration_ms=int(probe.duration_seconds * Decimal("1000")),
    )
    return replace(rendered, video=verified_video)


__all__ = ["HostedVerifiedVideoMediaSandbox"]
