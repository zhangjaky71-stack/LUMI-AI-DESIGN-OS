from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from lumi_video_generation.media_sandbox import (
    FfmpegArgvCompiler,
    FfmpegInvocation,
)
from lumi_video_generation.model import (
    CompiledShot,
    DurableVideoObject,
    GatewayVideoResult,
    ShotSpec,
    SourceImageRef,
    StoredVideoClip,
    TimelineClip,
    ValidationDecision,
    VideoMode,
    VideoProbeResult,
    VideoTaskSpec,
    VideoTimeline,
)
from lumi_video_generation.validation import CompositeVideoValidator


def spec(identity_refs=("identity-product",), brand="brand-v1"):
    source = SourceImageRef(
        asset_id="asset-1",
        asset_version="v1",
        durable_ref="asset:source:v1",
        checksum_sha256="a" * 64,
        rights_snapshot_id="rights-v1",
    )
    shot = ShotSpec(
        shot_id="s1",
        duration_seconds=Decimal("4"),
        prompt="hero motion",
        source_ref=source,
        identity_refs=identity_refs,
    )
    return VideoTaskSpec(
        organization_id="org-1",
        project_id="project-1",
        task_id="task-1",
        operation_id="op-1",
        mode=VideoMode.IMAGE_TO_VIDEO,
        width=1280,
        height=720,
        fps=30,
        shots=(shot,),
        brand_rule_snapshot_id=brand,
    )


def clip(*, width=1280, black_ratio="0"):
    return StoredVideoClip(
        shot_id="s1",
        object=DurableVideoObject(
            durable_ref="asset:clip:s1",
            bucket="generated-video",
            storage_key="video/s1.mp4",
            size_bytes=1024,
        ),
        checksum_sha256="b" * 64,
        probe=VideoProbeResult(
            mime_type="video/mp4",
            width=width,
            height=720,
            duration_seconds=Decimal("4"),
            decodable_frames=120,
            black_frame_ratio=Decimal(black_ratio),
        ),
        provider="mock",
        model="video-v1",
        provider_request_id="req-1",
    )


def test_identity_and_brand_require_validators_fail_closed():
    async def scenario():
        task = spec()
        shot = CompiledShot(0, task.shots[0], "operation")
        report = await CompositeVideoValidator().validate(
            spec=task,
            shot=shot,
            clip=clip(),
            provider_result=GatewayVideoResult(
                status="COMPLETED",
                provider="mock",
                model="video-v1",
                provider_request_id="req-1",
                output_ref="provider://clip",
            ),
        )
        assert report.decision is ValidationDecision.REJECT
        assert "VIDEO_IDENTITY_VALIDATOR_REQUIRED" in report.reason_codes
        assert "VIDEO_BRAND_VALIDATOR_REQUIRED" in report.reason_codes

    asyncio.run(scenario())


def test_provider_safety_and_black_frames_are_hard_rejections():
    async def scenario():
        task = spec(identity_refs=(), brand=None)
        shot = CompiledShot(0, task.shots[0], "operation")
        report = await CompositeVideoValidator().validate(
            spec=task,
            shot=shot,
            clip=clip(black_ratio="0.5"),
            provider_result=GatewayVideoResult(
                status="COMPLETED",
                provider="mock",
                model="video-v1",
                provider_request_id="req-1",
                output_ref="provider://clip",
                safety_metadata={"hard_rejected": True},
            ),
        )
        assert report.decision is ValidationDecision.REJECT
        assert "PROVIDER_SAFETY_HARD_REJECT" in report.reason_codes
        assert "VIDEO_BLACK_FRAME_RATIO_EXCEEDED" in report.reason_codes

    asyncio.run(scenario())


def test_ffmpeg_compiler_uses_argv_and_rejects_protocol_inputs():
    timeline = VideoTimeline(
        clips=(
            TimelineClip(
                "s1",
                "asset:clip:s1",
                Decimal("0"),
                Decimal("4"),
                "CUT",
            ),
        ),
        width=1280,
        height=720,
        fps=30,
    )
    compiler = FfmpegArgvCompiler()
    invocation = compiler.compile(
        timeline=timeline,
        local_clip_paths=("/sandbox/input/s1.mp4",),
        output_path="/sandbox/output/final.mp4",
    )
    assert invocation.shell is False
    assert invocation.argv[0] == "ffmpeg"
    with pytest.raises(ValueError, match="PROTOCOL"):
        compiler.compile(
            timeline=timeline,
            local_clip_paths=("https://evil.example/input.mp4",),
            output_path="/sandbox/output/final.mp4",
        )
    with pytest.raises(ValueError, match="TOKEN"):
        compiler.compile(
            timeline=timeline,
            local_clip_paths=("/sandbox/input/s1;touch-x.mp4",),
            output_path="/sandbox/output/final.mp4",
        )
    with pytest.raises(ValueError, match="SHELL"):
        FfmpegInvocation(("ffmpeg", "-version"), shell=True)


def test_durable_video_object_rejects_public_urls():
    with pytest.raises(ValueError, match="internal"):
        DurableVideoObject(
            durable_ref="https://cdn.example/video.mp4",
            bucket="generated-video",
            storage_key="video/final.mp4",
            size_bytes=1,
        )
    with pytest.raises(ValueError, match="cannot be a URL"):
        DurableVideoObject(
            durable_ref="asset:video:1",
            bucket="generated-video",
            storage_key="https://cdn.example/video.mp4",
            size_bytes=1,
        )
