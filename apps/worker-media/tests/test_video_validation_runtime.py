from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from lumi_video_generation.model import (
    CompiledShot,
    ShotSpec,
    StoredVideoClip,
    VideoProbeResult,
    VideoTaskSpec,
)
from lumi_worker_media.video_validation_runtime import HostedV1VideoValidator


def _fixture() -> tuple[VideoTaskSpec, CompiledShot, StoredVideoClip, VideoProbeResult]:
    shot = ShotSpec(
        shot_id="hero",
        duration_seconds=Decimal("4"),
        prompt="A clean product hero shot",
    )
    spec = VideoTaskSpec(
        organization_id=str(uuid4()),
        project_id=str(uuid4()),
        task_id=str(uuid4()),
        operation_id=str(uuid4()),
        mode="TEXT_TO_VIDEO",
        prompt=shot.prompt,
        duration_seconds=Decimal("4"),
        aspect_ratio="16:9",
        width=1280,
        height=720,
        fps=24,
        budget_limit_usd=Decimal("2"),
        code_git_sha="a" * 40,
        shots=(shot,),
    )
    compiled = CompiledShot(
        shot=shot,
        paid_operation_id=str(uuid4()),
        ordinal=1,
    )
    checksum = hashlib.sha256(b"provider-video").hexdigest()
    clip = StoredVideoClip(
        storage_key=f"generated/video/v1/{checksum}.mp4",
        checksum_sha256=checksum,
        mime_type="video/mp4",
        size_bytes=4096,
        width=1280,
        height=720,
        duration_ms=4000,
        durable_asset_ref=f"generated/video/v1/{checksum}.mp4",
        poster_frame_ref=None,
        tail_frame_ref=None,
        keyframe_refs=(),
    )
    probe = VideoProbeResult(
        decode_ok=True,
        mime_type="video/mp4",
        container="mov,mp4,m4a,3gp,3g2,mj2",
        video_codec="h264",
        width=1280,
        height=720,
        fps=Decimal("30"),
        duration_seconds=Decimal("4.000"),
        keyframe_refs=(),
        poster_frame_ref=None,
        tail_frame_ref=None,
        has_audio=True,
    )
    return spec, compiled, clip, probe


def _validate(
    spec: VideoTaskSpec,
    shot: CompiledShot,
    clip: StoredVideoClip,
    probe: VideoProbeResult,
    *,
    safety_metadata: dict[str, object] | None = None,
):
    return asyncio.run(
        HostedV1VideoValidator().validate_shot(
            spec=spec,
            shot=shot,
            clip=clip,
            probe=probe,
            safety_metadata=safety_metadata or {},
        )
    )


def test_hosted_raw_provider_fps_is_not_mistaken_for_final_output_fps() -> None:
    spec, shot, clip, probe = _fixture()
    assert probe.fps == Decimal("30")
    assert spec.fps == 24

    report = _validate(spec, shot, clip, probe)

    assert report.decision == "PASS"
    assert report.findings == ()


def test_hosted_raw_resolution_mismatch_still_rejects() -> None:
    spec, shot, clip, probe = _fixture()

    report = _validate(spec, shot, clip, replace(probe, width=720, height=1280))

    assert report.decision == "REJECT"
    assert [item.reason_code for item in report.findings] == ["VIDEO_RESOLUTION_MISMATCH"]


def test_hosted_raw_duration_mismatch_still_rejects() -> None:
    spec, shot, clip, probe = _fixture()

    report = _validate(spec, shot, clip, replace(probe, duration_seconds=Decimal("5")))

    assert report.decision == "REJECT"
    assert [item.reason_code for item in report.findings] == ["VIDEO_DURATION_MISMATCH"]


def test_hosted_raw_provider_safety_block_still_rejects() -> None:
    spec, shot, clip, probe = _fixture()

    report = _validate(
        spec,
        shot,
        clip,
        probe,
        safety_metadata={"blocked": True},
    )

    assert report.decision == "REJECT"
    assert [item.reason_code for item in report.findings] == ["VIDEO_PROVIDER_SAFETY_BLOCK"]
