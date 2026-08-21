from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from lumi_video_generation.model import (
    RenderedVideo,
    ShotSpec,
    StoredVideoClip,
    TimelineClip,
    VideoOutputSpec,
    VideoTaskSpec,
    VideoTimeline,
)

import lumi_worker_media.video_final_probe_runtime as final_probe_module
from lumi_worker_media.video_final_probe_runtime import HostedVerifiedVideoMediaSandbox


@dataclass(frozen=True)
class _Head:
    content_length: int
    content_type: str | None
    checksum_sha256_b64: str | None
    metadata: dict[str, str]


class _FakeStore:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[int, str, dict[str, str]]] = {}
        self.copies: list[tuple[str, str, str, str]] = []
        self.deleted: list[tuple[str, str]] = []

    def seed(self, bucket: str, key: str, *, size: int, content_type: str, checksum: str) -> None:
        self.objects[(bucket, key)] = (size, content_type, {"sha256": checksum})

    async def head(self, *, bucket: str, object_key: str) -> _Head:
        size, content_type, metadata = self.objects[(bucket, object_key)]
        return _Head(size, content_type, None, dict(metadata))

    async def copy(
        self,
        *,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> None:
        self.copies.append((source_bucket, source_key, destination_bucket, destination_key))
        self.objects[(destination_bucket, destination_key)] = self.objects[(source_bucket, source_key)]

    async def delete_candidate(self, *, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))
        self.objects.pop((bucket, object_key), None)


class _FakeRenderer:
    def __init__(self, rendered: RenderedVideo) -> None:
        self.rendered = rendered

    async def render(self, timeline: VideoTimeline) -> RenderedVideo:
        del timeline
        return self.rendered


class _ProbeAdapter:
    def __init__(self, store: _FakeStore) -> None:
        self.bucket = "lumi-assets"
        self.exchange_bucket = "lumi-sandbox"
        self.object_store = store
        self.sandbox_base_url = "http://sandbox-runtime.test:8080"
        self.sandbox_auth_secret = "s" * 64
        self.sandbox_timeout_seconds = 390.0


def _fixture() -> tuple[VideoTaskSpec, VideoTimeline, RenderedVideo, _FakeStore]:
    organization_id = str(uuid4())
    project_id = str(uuid4())
    task_id = str(uuid4())
    operation_id = str(uuid4())
    shot = ShotSpec(
        shot_id="hero",
        duration_seconds=Decimal("4"),
        prompt="A clean product hero shot",
    )
    spec = VideoTaskSpec(
        organization_id=organization_id,
        project_id=project_id,
        task_id=task_id,
        operation_id=operation_id,
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
    timeline = VideoTimeline(
        clips=(
            TimelineClip(
                shot_id="hero",
                artifact_version_id="artifact-version-1",
                durable_ref="generated/video/v1/source/clip.mp4",
                duration_seconds=Decimal("4"),
            ),
        ),
        overlays=(),
        audio_tracks=(),
        transitions=(),
        output_spec=VideoOutputSpec(width=1280, height=720, fps=24),
    )
    checksum = hashlib.sha256(b"final-video").hexdigest()
    key = (
        f"generated/video/v1/{organization_id}/{project_id}/"
        f"final/{checksum}.mp4"
    )
    # Deliberately bogus expected metadata. The final verifier must not trust it.
    rendered = RenderedVideo(
        video=StoredVideoClip(
            storage_key=key,
            checksum_sha256=checksum,
            mime_type="video/mp4",
            size_bytes=4096,
            width=1,
            height=1,
            duration_ms=1,
            durable_asset_ref=key,
            poster_frame_ref=None,
            tail_frame_ref=None,
            keyframe_refs=(),
        )
    )
    store = _FakeStore()
    store.seed(
        "lumi-assets",
        key,
        size=4096,
        content_type="video/mp4",
        checksum=checksum,
    )
    return spec, timeline, rendered, store


def _ffprobe_payload(
    *,
    fps: str = "24/1",
    width: int = 1280,
    height: int = 720,
    duration: str = "4.000",
    audio: bool = False,
) -> dict[str, Any]:
    streams: list[dict[str, object]] = [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": width,
            "height": height,
            "r_frame_rate": fps,
        }
    ]
    if audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    return {
        "exit_code": 0,
        "stdout": json.dumps(
            {
                "streams": streams,
                "format": {
                    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                    "duration": duration,
                },
            }
        ),
    }


def _verified_runtime(
    spec: VideoTaskSpec,
    rendered: RenderedVideo,
    store: _FakeStore,
) -> HostedVerifiedVideoMediaSandbox:
    return HostedVerifiedVideoMediaSandbox(
        spec=spec,
        renderer=_FakeRenderer(rendered),  # type: ignore[arg-type]
        probe_adapter=_ProbeAdapter(store),  # type: ignore[arg-type]
    )


def test_final_render_is_reprobed_and_expected_metadata_is_not_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, timeline, rendered, store = _fixture()
    seen: list[dict[str, object]] = []

    def fake_request(**kwargs: object) -> dict[str, object]:
        payload = kwargs["payload"]
        assert isinstance(payload, dict)
        seen.append(payload)
        assert payload["command"][-1] == "/sandbox/input/final.mp4"
        assert payload["exchange_outputs"] == []
        return _ffprobe_payload()

    monkeypatch.setattr(final_probe_module, "_sandbox_request", fake_request)
    verified = asyncio.run(_verified_runtime(spec, rendered, store).render(timeline))

    assert rendered.video.width == 1
    assert rendered.video.height == 1
    assert rendered.video.duration_ms == 1
    assert verified.video.width == 1280
    assert verified.video.height == 720
    assert verified.video.duration_ms == 4000
    assert len(seen) == 1
    assert any(copy[0] == "lumi-assets" and copy[2] == "lumi-sandbox" for copy in store.copies)
    assert any(bucket == "lumi-sandbox" for bucket, _key in store.deleted)


def test_final_render_fps_mismatch_fails_before_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, timeline, rendered, store = _fixture()
    monkeypatch.setattr(
        final_probe_module,
        "_sandbox_request",
        lambda **_: _ffprobe_payload(fps="30/1"),
    )
    with pytest.raises(RuntimeError, match="VIDEO_FINAL_FPS_MISMATCH"):
        asyncio.run(_verified_runtime(spec, rendered, store).render(timeline))


def test_final_render_unexpected_audio_fails_before_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, timeline, rendered, store = _fixture()
    monkeypatch.setattr(
        final_probe_module,
        "_sandbox_request",
        lambda **_: _ffprobe_payload(audio=True),
    )
    with pytest.raises(RuntimeError, match="VIDEO_FINAL_UNEXPECTED_AUDIO"):
        asyncio.run(_verified_runtime(spec, rendered, store).render(timeline))


def test_final_render_durable_checksum_mismatch_fails_before_ffprobe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, timeline, rendered, store = _fixture()
    key = rendered.video.storage_key
    store.seed(
        "lumi-assets",
        key,
        size=rendered.video.size_bytes,
        content_type="video/mp4",
        checksum="0" * 64,
    )
    called = False

    def should_not_run(**_: object) -> dict[str, object]:
        nonlocal called
        called = True
        return _ffprobe_payload()

    monkeypatch.setattr(final_probe_module, "_sandbox_request", should_not_run)
    with pytest.raises(RuntimeError, match="VIDEO_FINAL_DURABLE_IDENTITY_MISMATCH"):
        asyncio.run(_verified_runtime(spec, rendered, store).render(timeline))
    assert called is False
