from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from lumi_video_generation.media_sandbox import (
    FfmpegInvocation,
    SandboxLimits,
    TypedFfmpegSandbox,
)
from lumi_video_generation.model import TimelineClip, VideoOutputSpec, VideoTimeline
from lumi_worker_media.video_sandbox_runtime import SandboxExchangeMediaRuntime


@dataclass(frozen=True)
class _Head:
    content_length: int
    content_type: str | None
    checksum_sha256_b64: str | None
    metadata: dict[str, str]


class _FakeStore:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str, dict[str, str]]] = {}
        self.copies: list[tuple[str, str, str, str]] = []
        self.deleted: list[tuple[str, str]] = []

    def seed(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        checksum = hashlib.sha256(data).hexdigest()
        self.objects[(bucket, key)] = (data, content_type, {"sha256": checksum})

    async def head(self, *, bucket: str, object_key: str) -> _Head:
        data, content_type, metadata = self.objects[(bucket, object_key)]
        return _Head(
            content_length=len(data),
            content_type=content_type,
            checksum_sha256_b64=None,
            metadata=dict(metadata),
        )

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


class _CorruptingStageStore(_FakeStore):
    async def copy(
        self,
        *,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> None:
        await super().copy(
            source_bucket=source_bucket,
            source_key=source_key,
            destination_bucket=destination_bucket,
            destination_key=destination_key,
        )
        if destination_bucket == "lumi-sandbox":
            data, content_type, _metadata = self.objects[(destination_bucket, destination_key)]
            self.objects[(destination_bucket, destination_key)] = (
                data,
                content_type,
                {"sha256": "0" * 64},
            )


class _FakeSandboxRuntime(SandboxExchangeMediaRuntime):
    def __init__(self, *, store: _FakeStore, **kwargs: Any) -> None:
        super().__init__(object_store=store, **kwargs)  # type: ignore[arg-type]
        self.payloads: list[dict[str, Any]] = []
        self.store = store

    def _request(self, body: bytes) -> dict[str, Any]:
        payload = json.loads(body.decode("utf-8"))
        self.payloads.append(payload)
        assert payload["agent_run_id"] == self.task_id
        assert payload["timeout_seconds"] == 300
        assert len(payload["exchange_inputs"]) == 1
        assert len(payload["exchange_outputs"]) == 1
        assert all("/sandbox/" in token or not token.startswith("/") for token in payload["command"])
        output = payload["exchange_outputs"][0]
        key = output["exchange_key"]
        rendered = b"rendered-mp4" * 1024
        self.store.seed(self.exchange_bucket, key, rendered, "video/mp4")
        return {"sandbox_id": str(uuid4()), "exit_code": 0}


def _runtime(store: _FakeStore) -> _FakeSandboxRuntime:
    return _FakeSandboxRuntime(
        store=store,
        base_url="http://sandbox-runtime.test:8080",
        auth_secret="s" * 64,
        asset_bucket="lumi-assets",
        exchange_bucket="lumi-sandbox",
        organization_id=str(uuid4()),
        project_id=str(uuid4()),
        task_id=str(uuid4()),
        operation_id=str(uuid4()),
    )


def test_typed_ffmpeg_uses_exchange_bucket_and_promotes_final_video() -> None:
    store = _FakeStore()
    asset_bucket = "lumi-assets"
    exchange_bucket = "lumi-sandbox"
    source_key = "generated/video/v1/org/project/source/clip.mp4"
    store.seed(asset_bucket, source_key, b"source-mp4" * 1024, "video/mp4")
    task_id = str(uuid4())
    runtime = _FakeSandboxRuntime(
        store=store,
        base_url="http://sandbox-runtime.test:8080",
        auth_secret="s" * 64,
        asset_bucket=asset_bucket,
        exchange_bucket=exchange_bucket,
        organization_id=str(uuid4()),
        project_id=str(uuid4()),
        task_id=task_id,
        operation_id=str(uuid4()),
    )
    timeline = VideoTimeline(
        clips=(
            TimelineClip(
                shot_id="shot-001",
                artifact_version_id=str(uuid4()),
                durable_ref=source_key,
                duration_seconds=Decimal("4"),
            ),
        ),
        overlays=(),
        audio_tracks=(),
        transitions=(),
        output_spec=VideoOutputSpec(width=1280, height=720, fps=30),
    )

    rendered = asyncio.run(
        TypedFfmpegSandbox(executor=runtime, resolver=runtime).render(timeline)
    )

    assert len(runtime.payloads) == 1
    payload = runtime.payloads[0]
    manifest = payload["exchange_inputs"][0]
    assert manifest["path"].startswith("input/")
    assert manifest["expected_sha256"] == hashlib.sha256(b"source-mp4" * 1024).hexdigest()
    assert payload["exchange_outputs"][0]["path"] == "output/render.mp4"
    assert payload["exchange_outputs"][0]["content_type"] == "video/mp4"
    assert rendered.video.width == 1280
    assert rendered.video.height == 720
    assert rendered.video.duration_ms == 4000
    assert rendered.video.mime_type == "video/mp4"
    assert rendered.video.durable_asset_ref == rendered.video.storage_key
    assert rendered.video.storage_key.startswith("generated/video/v1/")
    assert (asset_bucket, rendered.video.storage_key) in store.objects
    assert any(copy[0] == asset_bucket and copy[2] == exchange_bucket for copy in store.copies)
    assert any(copy[0] == exchange_bucket and copy[2] == asset_bucket for copy in store.copies)
    assert store.deleted
    assert not any(bucket == exchange_bucket for bucket, _ in store.objects)


def test_input_stage_checksum_mismatch_fails_before_sandbox_http() -> None:
    store = _CorruptingStageStore()
    source_key = "generated/video/v1/org/project/source/clip.mp4"
    store.seed("lumi-assets", source_key, b"source-mp4" * 32, "video/mp4")
    runtime = _runtime(store)
    input_path = runtime.resolve_readonly(source_key)
    output_path = runtime.allocate_output(".mp4")
    invocation = FfmpegInvocation(
        argv=("ffmpeg", "-i", input_path, output_path),
        limits=SandboxLimits(network_disabled=True),
        output_path=output_path,
    )
    try:
        asyncio.run(runtime.execute(invocation))
    except RuntimeError as exc:
        assert str(exc) == "VIDEO_SANDBOX_STAGE_CHECKSUM_MISMATCH"
    else:
        raise AssertionError("checksum drift must fail closed before Sandbox HTTP")
    assert runtime.payloads == []
    assert store.deleted


def test_sandbox_bridge_rejects_network_enabled_invocation() -> None:
    runtime = _runtime(_FakeStore())
    runtime.allocate_output(".mp4")
    invocation = FfmpegInvocation(
        argv=("ffmpeg", "-version"),
        limits=SandboxLimits(network_disabled=False),
        output_path="/sandbox/output/render.mp4",
    )
    try:
        asyncio.run(runtime.execute(invocation))
    except RuntimeError as exc:
        assert str(exc) == "VIDEO_SANDBOX_NETWORK_MUST_BE_DISABLED"
    else:
        raise AssertionError("network-enabled media invocation must fail closed")
