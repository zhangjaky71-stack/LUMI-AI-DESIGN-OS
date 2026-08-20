from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import pytest
from lumi_video_generation.model import CompiledShot, ShotSpec, VideoTaskSpec

import lumi_worker_media.video_generation_ports as ports_module
from lumi_worker_media.video_generation_ports import HostedVideoOutputAdapter


@dataclass(frozen=True)
class _Head:
    content_length: int
    content_type: str | None
    checksum_sha256_b64: str | None
    metadata: dict[str, str]


class _FakeStore:
    def __init__(self, *, corrupt_promotion: bool = False) -> None:
        self.objects: dict[tuple[str, str], tuple[int, str, dict[str, str]]] = {}
        self.copies: list[tuple[str, str, str, str]] = []
        self.deleted: list[tuple[str, str]] = []
        self.corrupt_promotion = corrupt_promotion

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
        row = self.objects[(source_bucket, source_key)]
        if (
            self.corrupt_promotion
            and source_bucket == destination_bucket == "lumi-assets"
            and destination_key.startswith("generated/video/v1/")
        ):
            row = (row[0], row[1], {"sha256": "0" * 64})
        self.objects[(destination_bucket, destination_key)] = row

    async def delete_candidate(self, *, bucket: str, object_key: str) -> None:
        self.deleted.append((bucket, object_key))
        self.objects.pop((bucket, object_key), None)


def _spec() -> tuple[VideoTaskSpec, CompiledShot]:
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
    return spec, CompiledShot(
        shot=shot,
        paid_operation_id=str(uuid4()),
        ordinal=1,
    )


def _ffprobe_payload() -> dict[str, object]:
    return {
        "exit_code": 0,
        "stdout": json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1280,
                        "height": 720,
                        "r_frame_rate": "24/1",
                    }
                ],
                "format": {
                    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                    "duration": "4.000",
                },
            }
        ),
    }


def _adapter(store: _FakeStore) -> HostedVideoOutputAdapter:
    return HostedVideoOutputAdapter(
        bucket="lumi-assets",
        exchange_bucket="lumi-sandbox",
        object_store=store,  # type: ignore[arg-type]
        sandbox_base_url="http://sandbox-runtime.test:8080",
        sandbox_auth_secret="s" * 64,
    )


def test_provider_output_is_probed_in_exchange_then_promoted_by_server_side_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, shot = _spec()
    store = _FakeStore()
    checksum = hashlib.sha256(b"provider-video").hexdigest()
    source_key = f"provider-output/v1/async/a/b/c/{checksum}.mp4"
    store.seed(
        "lumi-assets",
        source_key,
        size=4096,
        content_type="video/mp4",
        checksum=checksum,
    )
    seen: list[dict[str, object]] = []

    def fake_sandbox_request(**kwargs: object) -> dict[str, object]:
        payload = kwargs["payload"]
        assert isinstance(payload, dict)
        seen.append(payload)
        assert payload["command"][-1] == "/sandbox/input/provider.mp4"
        assert payload["exchange_outputs"] == []
        return _ffprobe_payload()

    monkeypatch.setattr(ports_module, "_sandbox_request", fake_sandbox_request)
    clip, probe = asyncio.run(
        _adapter(store).materialize_and_probe(
            spec=spec,
            shot=shot,
            output_ref=f"s3://lumi-assets/{source_key}",
            declared_mime_type="video/mp4",
        )
    )

    assert probe.decode_ok is True
    assert clip.checksum_sha256 == checksum
    assert clip.width == 1280
    assert clip.height == 720
    assert clip.duration_ms == 4000
    assert clip.storage_key.startswith(
        f"generated/video/v1/{spec.organization_id}/{spec.project_id}/shots/"
    )
    assert len(seen) == 1
    assert any(copy[0] == "lumi-assets" and copy[2] == "lumi-sandbox" for copy in store.copies)
    assert any(
        copy[0] == "lumi-assets"
        and copy[2] == "lumi-assets"
        and copy[3] == clip.storage_key
        for copy in store.copies
    )
    assert ("lumi-assets", source_key) in store.deleted
    assert any(bucket == "lumi-sandbox" for bucket, _key in store.deleted)


def test_provider_output_wrong_bucket_fails_before_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    spec, shot = _spec()
    store = _FakeStore()
    monkeypatch.setattr(ports_module, "_sandbox_request", lambda **_: _ffprobe_payload())
    with pytest.raises(ValueError, match="VIDEO_PROVIDER_OUTPUT_BUCKET_MISMATCH"):
        asyncio.run(
            _adapter(store).materialize_and_probe(
                spec=spec,
                shot=shot,
                output_ref="s3://attacker-bucket/provider-output/v1/async/a/b/c/file.mp4",
                declared_mime_type="video/mp4",
            )
        )
    assert store.copies == []


def test_durable_promotion_checksum_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec, shot = _spec()
    store = _FakeStore(corrupt_promotion=True)
    checksum = hashlib.sha256(b"provider-video").hexdigest()
    source_key = f"provider-output/v1/async/a/b/c/{checksum}.mp4"
    store.seed(
        "lumi-assets",
        source_key,
        size=4096,
        content_type="video/mp4",
        checksum=checksum,
    )
    monkeypatch.setattr(ports_module, "_sandbox_request", lambda **_: _ffprobe_payload())
    with pytest.raises(RuntimeError, match="VIDEO_PROVIDER_OUTPUT_PROMOTION_MISMATCH"):
        asyncio.run(
            _adapter(store).materialize_and_probe(
                spec=spec,
                shot=shot,
                output_ref=f"s3://lumi-assets/{source_key}",
                declared_mime_type="video/mp4",
            )
        )
    assert ("lumi-assets", source_key) in store.deleted
