from __future__ import annotations

import asyncio
import hashlib
from decimal import Decimal

import pytest

from lumi_video_generation.model import CompiledShot, StoredVideoClip, VideoProbeResult, VideoTaskSpec
from lumi_video_generation.output_adapter import StagedProviderVideo, VerifiedVideoOutputAdapter
from lumi_video_generation.storyboard import compile_storyboard

ORG = "00000000-0000-0000-0000-000000000001"
PROJECT = "00000000-0000-0000-0000-000000000002"
TASK = "00000000-0000-0000-0000-000000000003"
OPERATION = "00000000-0000-0000-0000-000000000004"


def _spec() -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        mode="TEXT_TO_VIDEO",
        prompt="video output adapter test",
        duration_seconds=Decimal("2"),
        aspect_ratio="16:9",
        width=1600,
        height=900,
        fps=24,
        budget_limit_usd=Decimal("1"),
        code_git_sha="a" * 40,
        quality_retry_limit=0,
    )


class Fetcher:
    async def fetch_to_staging(self, *, source_ref: str, declared_mime_type: str | None, max_bytes: int) -> StagedProviderVideo:
        assert source_ref.startswith("https://provider.example/")
        assert max_bytes > 0
        digest = hashlib.sha256(b"provider-video").hexdigest()
        return StagedProviderVideo(
            staging_key="staging/video/provider-job-1.mp4",
            checksum_sha256=digest,
            size_bytes=2048,
            declared_mime_type=declared_mime_type,
        )


class Probe:
    async def probe(self, *, staging_key: str) -> VideoProbeResult:
        assert staging_key == "staging/video/provider-job-1.mp4"
        return VideoProbeResult(
            decode_ok=True,
            mime_type="video/mp4",
            container="mp4",
            video_codec="h264",
            width=1600,
            height=900,
            fps=Decimal("24"),
            duration_seconds=Decimal("2"),
            keyframe_refs=("asset:keyframe:1",),
            poster_frame_ref="asset:poster:1",
            tail_frame_ref="asset:tail:1",
        )


class Store:
    def __init__(self, *, corrupt_checksum: bool = False) -> None:
        self.discarded: list[str] = []
        self.corrupt_checksum = corrupt_checksum

    async def promote(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        staged: StagedProviderVideo,
        probe: VideoProbeResult,
    ) -> StoredVideoClip:
        del spec, shot
        return StoredVideoClip(
            storage_key="video/clips/durable.mp4",
            checksum_sha256="f" * 64 if self.corrupt_checksum else staged.checksum_sha256,
            mime_type="video/mp4",
            size_bytes=staged.size_bytes,
            width=probe.width,
            height=probe.height,
            duration_ms=2000,
            durable_asset_ref="asset:video:durable",
            poster_frame_ref=probe.poster_frame_ref,
            tail_frame_ref=probe.tail_frame_ref,
            keyframe_refs=probe.keyframe_refs,
        )

    async def discard_staging(self, staging_key: str) -> None:
        self.discarded.append(staging_key)


def test_provider_url_stops_at_staging_and_durable_output_is_checksum_verified() -> None:
    store = Store()
    adapter = VerifiedVideoOutputAdapter(fetcher=Fetcher(), probe_worker=Probe(), store=store)
    spec = _spec()
    shot = compile_storyboard(spec).shots[0]
    stored, probe = asyncio.run(adapter.materialize_and_probe(
        spec=spec,
        shot=shot,
        output_ref="https://provider.example/signed/output.mp4?token=secret",
        declared_mime_type="video/mp4",
    ))
    assert stored.storage_key == "video/clips/durable.mp4"
    assert "://" not in stored.storage_key
    assert probe.decode_ok
    assert store.discarded == ["staging/video/provider-job-1.mp4"]


def test_staging_is_cleaned_even_when_durable_checksum_mismatch_fails() -> None:
    store = Store(corrupt_checksum=True)
    adapter = VerifiedVideoOutputAdapter(fetcher=Fetcher(), probe_worker=Probe(), store=store)
    spec = _spec()
    shot = compile_storyboard(spec).shots[0]
    with pytest.raises(ValueError, match="VIDEO_DURABLE_CHECKSUM_MISMATCH"):
        asyncio.run(adapter.materialize_and_probe(
            spec=spec,
            shot=shot,
            output_ref="https://provider.example/output.mp4",
            declared_mime_type="video/mp4",
        ))
    assert store.discarded == ["staging/video/provider-job-1.mp4"]
