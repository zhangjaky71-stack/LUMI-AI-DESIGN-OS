from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from lumi_asset_storage.s3 import S3ObjectStore
from lumi_video_generation.media_sandbox import FfmpegInvocation
from lumi_video_generation.model import RenderedVideo, StoredVideoClip, VideoTimeline

_EXECUTE_PATH = "/internal/v1/sandbox/execute"
_CALLER = "worker-media"
_MAX_SOURCE_BYTES = 4 * 1024 * 1024 * 1024
_MAX_RENDER_BYTES = 8 * 1024 * 1024 * 1024
_ALLOWED_INPUT_MIME = frozenset(
    {
        "video/mp4",
        "audio/mpeg",
        "audio/mp4",
        "audio/aac",
        "audio/wav",
        "image/png",
        "image/jpeg",
        "image/webp",
    }
)


@dataclass(frozen=True, slots=True)
class _InputBinding:
    durable_ref: str
    logical_path: str
    exchange_key: str


@dataclass(frozen=True, slots=True)
class _OutputBinding:
    logical_path: str
    exchange_key: str


class SandboxExchangeMediaRuntime:
    """Invocation-local NODE-48 SandboxExecutor + SandboxPathResolver.

    Durable media stays in the canonical assets bucket. Before execution, source
    objects are server-side copied into the sandbox exchange bucket. The isolated
    Fargate child can read/write only the exchange prefix and has no business asset
    bucket credential. Rendered output is promoted back with another server-side
    copy after checksum/size validation.
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth_secret: str,
        asset_bucket: str,
        exchange_bucket: str,
        object_store: S3ObjectStore,
        organization_id: str,
        project_id: str,
        task_id: str,
        operation_id: str,
        timeout_seconds: float = 390.0,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("VIDEO_SANDBOX_URL_INVALID")
        if len(auth_secret.encode("utf-8")) < 32 or "\x00" in auth_secret:
            raise ValueError("VIDEO_SANDBOX_AUTH_SECRET_INVALID")
        for name, value in (
            ("asset_bucket", asset_bucket),
            ("exchange_bucket", exchange_bucket),
        ):
            if not value or value != value.strip() or "/" in value:
                raise ValueError(f"VIDEO_SANDBOX_{name.upper()}_INVALID")
        if asset_bucket == exchange_bucket:
            raise ValueError("VIDEO_SANDBOX_BUCKET_BOUNDARY_REQUIRED")
        for name, value in (
            ("organization_id", organization_id),
            ("project_id", project_id),
            ("task_id", task_id),
            ("operation_id", operation_id),
        ):
            if not value or "/" in value or "\x00" in value:
                raise ValueError(f"VIDEO_SANDBOX_{name.upper()}_INVALID")
        if timeout_seconds <= 0:
            raise ValueError("VIDEO_SANDBOX_HTTP_TIMEOUT_INVALID")
        self.base_url = base_url.rstrip("/")
        self.auth_secret = auth_secret
        self.asset_bucket = asset_bucket
        self.exchange_bucket = exchange_bucket
        self.object_store = object_store
        self.organization_id = organization_id
        self.project_id = project_id
        self.task_id = task_id
        self.operation_id = operation_id
        self.timeout_seconds = timeout_seconds
        scope = hashlib.sha256(
            f"{organization_id}\x00{project_id}\x00{task_id}\x00{operation_id}".encode("utf-8")
        ).hexdigest()
        self.exchange_prefix = f"sandbox-exchange/v1/{organization_id}/{scope}"
        self._inputs: dict[str, _InputBinding] = {}
        self._output: _OutputBinding | None = None
        self._staged_exchange_keys: set[str] = set()
        self._executed = False

    @classmethod
    def from_env(
        cls,
        *,
        organization_id: str,
        project_id: str,
        task_id: str,
        operation_id: str,
    ) -> SandboxExchangeMediaRuntime:
        region = os.getenv("LUMI_S3_REGION") or os.getenv("AWS_REGION") or "us-east-1"
        return cls(
            base_url=_required_env("LUMI_SANDBOX_RUNTIME_URL"),
            auth_secret=_required_env("LUMI_SANDBOX_RUNTIME_AUTH_SECRET", max_length=8192),
            asset_bucket=_required_env("LUMI_S3_BUCKET", max_length=255),
            exchange_bucket=_required_env("LUMI_SANDBOX_EXCHANGE_BUCKET", max_length=255),
            object_store=S3ObjectStore(
                endpoint_url=os.getenv("LUMI_S3_ENDPOINT_URL"),
                region_name=region,
                access_key_id=os.getenv("LUMI_S3_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("LUMI_S3_SECRET_ACCESS_KEY"),
                force_path_style=_env_bool("LUMI_S3_FORCE_PATH_STYLE"),
            ),
            organization_id=organization_id,
            project_id=project_id,
            task_id=task_id,
            operation_id=operation_id,
        )

    def resolve_readonly(self, durable_ref: str) -> str:
        source_key = _durable_object_key(durable_ref)
        existing = self._inputs.get(source_key)
        if existing is not None:
            return existing.logical_path
        token = hashlib.sha256(source_key.encode("utf-8")).hexdigest()
        suffix = _safe_suffix(source_key)
        logical_path = f"/sandbox/input/{token[:32]}{suffix}"
        exchange_key = f"{self.exchange_prefix}/input/{token}{suffix}"
        binding = _InputBinding(
            durable_ref=source_key,
            logical_path=logical_path,
            exchange_key=exchange_key,
        )
        self._inputs[source_key] = binding
        return logical_path

    def allocate_output(self, suffix: str) -> str:
        if suffix != ".mp4":
            raise ValueError("VIDEO_SANDBOX_OUTPUT_SUFFIX_UNSUPPORTED")
        if self._output is not None:
            raise RuntimeError("VIDEO_SANDBOX_OUTPUT_ALREADY_ALLOCATED")
        token = hashlib.sha256(
            f"{self.operation_id}\x00rendered-video".encode("utf-8")
        ).hexdigest()
        binding = _OutputBinding(
            logical_path="/sandbox/output/render.mp4",
            exchange_key=f"{self.exchange_prefix}/output/{token}.mp4",
        )
        self._output = binding
        return binding.logical_path

    async def execute(self, invocation: FfmpegInvocation) -> None:
        if self._executed:
            raise RuntimeError("VIDEO_SANDBOX_INVOCATION_ALREADY_EXECUTED")
        if self._output is None or invocation.output_path != self._output.logical_path:
            raise RuntimeError("VIDEO_SANDBOX_OUTPUT_BINDING_MISMATCH")
        if not invocation.limits.network_disabled:
            raise RuntimeError("VIDEO_SANDBOX_NETWORK_MUST_BE_DISABLED")
        if invocation.limits.timeout_seconds > 3600:
            raise RuntimeError("VIDEO_SANDBOX_TIMEOUT_OUT_OF_RANGE")
        input_manifest: list[dict[str, object]] = []
        try:
            for binding in self._inputs.values():
                head = await self.object_store.head(
                    bucket=self.asset_bucket,
                    object_key=binding.durable_ref,
                )
                if head.content_length <= 0 or head.content_length > _MAX_SOURCE_BYTES:
                    raise ValueError("VIDEO_SANDBOX_SOURCE_SIZE_INVALID")
                if head.content_type not in _ALLOWED_INPUT_MIME:
                    raise ValueError("VIDEO_SANDBOX_SOURCE_MIME_UNSUPPORTED")
                checksum = _head_sha256(head.checksum_sha256_b64, head.metadata)
                await self.object_store.copy(
                    source_bucket=self.asset_bucket,
                    source_key=binding.durable_ref,
                    destination_bucket=self.exchange_bucket,
                    destination_key=binding.exchange_key,
                )
                self._staged_exchange_keys.add(binding.exchange_key)
                staged = await self.object_store.head(
                    bucket=self.exchange_bucket,
                    object_key=binding.exchange_key,
                )
                if staged.content_length != head.content_length:
                    raise RuntimeError("VIDEO_SANDBOX_STAGE_SIZE_MISMATCH")
                staged_checksum = _head_sha256(staged.checksum_sha256_b64, staged.metadata)
                if staged_checksum != checksum:
                    raise RuntimeError("VIDEO_SANDBOX_STAGE_CHECKSUM_MISMATCH")
                input_manifest.append(
                    {
                        "exchange_key": binding.exchange_key,
                        "path": binding.logical_path.removeprefix("/sandbox/"),
                        "max_bytes": head.content_length,
                        "expected_sha256": checksum,
                    }
                )

            output = self._output
            payload = {
                "organization_id": self.organization_id,
                # SandboxSpec requires an agent_run identity. For media execution the
                # canonical task UUID is the execution identity; it carries no provider
                # credential and remains scoped by organization in the exchange prefix.
                "agent_run_id": self.task_id,
                "command": list(invocation.argv),
                "timeout_seconds": invocation.limits.timeout_seconds,
                "exchange_inputs": input_manifest,
                "exchange_outputs": [
                    {
                        "exchange_key": output.exchange_key,
                        "path": output.logical_path.removeprefix("/sandbox/"),
                        "max_bytes": _MAX_RENDER_BYTES,
                        "content_type": "video/mp4",
                    }
                ],
            }
            body = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            response = await asyncio.to_thread(self._request, body)
            if response.get("exit_code") != 0:
                raise RuntimeError("VIDEO_SANDBOX_FFMPEG_FAILED")
            self._staged_exchange_keys.add(output.exchange_key)
            rendered_head = await self.object_store.head(
                bucket=self.exchange_bucket,
                object_key=output.exchange_key,
            )
            if rendered_head.content_length <= 0 or rendered_head.content_length > _MAX_RENDER_BYTES:
                raise RuntimeError("VIDEO_SANDBOX_RENDER_SIZE_INVALID")
            if rendered_head.content_type != "video/mp4":
                raise RuntimeError("VIDEO_SANDBOX_RENDER_MIME_INVALID")
            _head_sha256(rendered_head.checksum_sha256_b64, rendered_head.metadata)
            self._executed = True
        except Exception:
            await self._cleanup_exchange()
            raise

    async def ingest_rendered_video(
        self,
        path: str,
        timeline: VideoTimeline,
    ) -> RenderedVideo:
        output = self._output
        if not self._executed or output is None or path != output.logical_path:
            raise RuntimeError("VIDEO_SANDBOX_RENDER_NOT_EXECUTED")
        try:
            head = await self.object_store.head(
                bucket=self.exchange_bucket,
                object_key=output.exchange_key,
            )
            checksum = _head_sha256(head.checksum_sha256_b64, head.metadata)
            if head.content_length <= 0 or head.content_length > _MAX_RENDER_BYTES:
                raise RuntimeError("VIDEO_SANDBOX_RENDER_SIZE_INVALID")
            scope = hashlib.sha256(
                f"{self.task_id}\x00{self.operation_id}".encode("utf-8")
            ).hexdigest()
            durable_key = (
                f"generated/video/v1/{self.organization_id}/{self.project_id}/"
                f"{scope}/final/{checksum}.mp4"
            )
            await self.object_store.copy(
                source_bucket=self.exchange_bucket,
                source_key=output.exchange_key,
                destination_bucket=self.asset_bucket,
                destination_key=durable_key,
            )
            durable = await self.object_store.head(
                bucket=self.asset_bucket,
                object_key=durable_key,
            )
            durable_checksum = _head_sha256(durable.checksum_sha256_b64, durable.metadata)
            if durable.content_length != head.content_length or durable_checksum != checksum:
                raise RuntimeError("VIDEO_SANDBOX_DURABLE_PROMOTION_MISMATCH")
            duration_seconds = sum(
                (clip.duration_seconds for clip in timeline.clips),
                Decimal("0"),
            )
            duration_ms = int(duration_seconds * Decimal("1000"))
            clip = StoredVideoClip(
                storage_key=durable_key,
                checksum_sha256=checksum,
                mime_type="video/mp4",
                size_bytes=durable.content_length,
                width=timeline.output_spec.width,
                height=timeline.output_spec.height,
                duration_ms=duration_ms,
                durable_asset_ref=durable_key,
                poster_frame_ref=None,
                tail_frame_ref=None,
                keyframe_refs=(),
            )
            return RenderedVideo(video=clip)
        finally:
            await self._cleanup_exchange()

    def _request(self, body: bytes) -> dict[str, Any]:
        timestamp = int(time.time())
        body_hash = hashlib.sha256(body).hexdigest()
        canonical = f"{_CALLER}\n{timestamp}\nPOST\n{_EXECUTE_PATH}\n{body_hash}".encode(
            "utf-8"
        )
        signature = hmac.new(
            self.auth_secret.encode("utf-8"),
            canonical,
            hashlib.sha256,
        ).hexdigest()
        request = urllib.request.Request(
            f"{self.base_url}{_EXECUTE_PATH}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Lumi-Service": _CALLER,
                "X-Lumi-Timestamp": str(timestamp),
                "X-Lumi-Signature": signature,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                status = int(response.status)
                raw = response.read(1024 * 1024 + 1)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RuntimeError("VIDEO_SANDBOX_RESPONSE_TOO_LARGE")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("VIDEO_SANDBOX_RESPONSE_INVALID") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("VIDEO_SANDBOX_RESPONSE_INVALID")
        if not 200 <= status < 300:
            code = payload.get("code")
            raise RuntimeError(
                code if isinstance(code, str) and code else "VIDEO_SANDBOX_HTTP_ERROR"
            )
        exit_code = payload.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise RuntimeError("VIDEO_SANDBOX_EXIT_CODE_INVALID")
        sandbox_id = payload.get("sandbox_id")
        if not isinstance(sandbox_id, str) or not sandbox_id:
            raise RuntimeError("VIDEO_SANDBOX_ID_INVALID")
        return payload

    async def _cleanup_exchange(self) -> None:
        keys = tuple(self._staged_exchange_keys)
        self._staged_exchange_keys.clear()
        for key in keys:
            try:
                await self.object_store.delete_candidate(
                    bucket=self.exchange_bucket,
                    object_key=key,
                )
            except Exception:
                # Cleanup failure must not overwrite the primary execution result.
                pass


def _durable_object_key(value: str) -> str:
    if (
        not value
        or value.startswith("/")
        or "://" in value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
        or "//" in value
        or "/../" in value
        or value.endswith("/..")
        or len(value) > 1024
    ):
        raise ValueError("VIDEO_SANDBOX_DURABLE_REF_INVALID")
    return value


def _safe_suffix(object_key: str) -> str:
    leaf = object_key.rsplit("/", 1)[-1]
    if "." not in leaf:
        return ".bin"
    suffix = "." + leaf.rsplit(".", 1)[-1].lower()
    if suffix not in {".mp4", ".mp3", ".m4a", ".aac", ".wav", ".png", ".jpg", ".jpeg", ".webp"}:
        return ".bin"
    return suffix


def _head_sha256(checksum_b64: str | None, metadata: dict[str, str]) -> str:
    metadata_checksum = metadata.get("sha256") or metadata.get("lumi-checksum-sha256")
    if metadata_checksum is not None:
        value = metadata_checksum.lower()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise RuntimeError("VIDEO_SANDBOX_SHA256_METADATA_INVALID")
        return value
    if checksum_b64:
        try:
            raw = base64.b64decode(checksum_b64, validate=True)
        except Exception as exc:
            raise RuntimeError("VIDEO_SANDBOX_SHA256_HEADER_INVALID") from exc
        if len(raw) != 32:
            raise RuntimeError("VIDEO_SANDBOX_SHA256_HEADER_INVALID")
        return raw.hex()
    raise RuntimeError("VIDEO_SANDBOX_SHA256_REQUIRED")


def _required_env(name: str, *, max_length: int = 4096) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _env_bool(name: str) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if raw in {"", "0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError(f"{name}_INVALID")
