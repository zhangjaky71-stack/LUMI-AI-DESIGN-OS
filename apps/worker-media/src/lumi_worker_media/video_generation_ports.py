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
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from uuid import UUID, uuid5

import asyncpg
from lumi_asset_storage.s3 import S3ObjectStore
from lumi_video_generation import CompositeVideoValidator, TypedFfmpegSandbox
from lumi_video_generation.model import (
    CompiledShot,
    RenderedVideo,
    StoredVideoClip,
    VideoProbeResult,
    VideoTaskSpec,
    VideoTimeline,
)

from .video_sandbox_runtime import SandboxExchangeMediaRuntime

_MAX_PROVIDER_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
_EXECUTE_PATH = "/internal/v1/sandbox/execute"
_CALLER = "worker-media"


class HostedVideoOutputAdapter:
    """Materialize private Model Gateway video outputs without public URLs or Worker downloads.

    Provider video content is already staged by Model Gateway in the private assets
    bucket under provider-output/v1/async/. This adapter verifies that private ref,
    probes it through the network-disabled Sandbox Runtime, then promotes the exact
    object into the canonical generated/video/v1 namespace by S3 server-side copy.
    """

    def __init__(
        self,
        *,
        bucket: str,
        exchange_bucket: str,
        object_store: S3ObjectStore,
        sandbox_base_url: str,
        sandbox_auth_secret: str,
        sandbox_timeout_seconds: float = 390.0,
    ) -> None:
        for name, value in (("bucket", bucket), ("exchange_bucket", exchange_bucket)):
            if not value or value != value.strip() or "/" in value:
                raise ValueError(f"VIDEO_OUTPUT_{name.upper()}_INVALID")
        if bucket == exchange_bucket:
            raise ValueError("VIDEO_OUTPUT_BUCKET_BOUNDARY_REQUIRED")
        if not sandbox_base_url.startswith(("http://", "https://")):
            raise ValueError("VIDEO_OUTPUT_SANDBOX_URL_INVALID")
        if len(sandbox_auth_secret.encode("utf-8")) < 32 or "\x00" in sandbox_auth_secret:
            raise ValueError("VIDEO_OUTPUT_SANDBOX_SECRET_INVALID")
        if sandbox_timeout_seconds <= 0:
            raise ValueError("VIDEO_OUTPUT_SANDBOX_TIMEOUT_INVALID")
        self.bucket = bucket
        self.exchange_bucket = exchange_bucket
        self.object_store = object_store
        self.sandbox_base_url = sandbox_base_url.rstrip("/")
        self.sandbox_auth_secret = sandbox_auth_secret
        self.sandbox_timeout_seconds = sandbox_timeout_seconds

    @classmethod
    def from_env(cls) -> HostedVideoOutputAdapter:
        region = os.getenv("LUMI_S3_REGION") or os.getenv("AWS_REGION") or "us-east-1"
        return cls(
            bucket=_required_env("LUMI_S3_BUCKET", max_length=255),
            exchange_bucket=_required_env("LUMI_SANDBOX_EXCHANGE_BUCKET", max_length=255),
            object_store=S3ObjectStore(
                endpoint_url=os.getenv("LUMI_S3_ENDPOINT_URL"),
                region_name=region,
                access_key_id=os.getenv("LUMI_S3_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("LUMI_S3_SECRET_ACCESS_KEY"),
                force_path_style=_env_bool("LUMI_S3_FORCE_PATH_STYLE"),
            ),
            sandbox_base_url=_required_env("LUMI_SANDBOX_RUNTIME_URL"),
            sandbox_auth_secret=_required_env(
                "LUMI_SANDBOX_RUNTIME_AUTH_SECRET",
                max_length=8192,
            ),
        )

    async def materialize_and_probe(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        output_ref: str,
        declared_mime_type: str | None,
    ) -> tuple[StoredVideoClip, VideoProbeResult]:
        if declared_mime_type not in {None, "video/mp4"}:
            raise ValueError("VIDEO_PROVIDER_DECLARED_MIME_UNSUPPORTED")
        source_key = _provider_output_key(output_ref, bucket=self.bucket)
        source = await self.object_store.head(bucket=self.bucket, object_key=source_key)
        if source.content_length <= 0 or source.content_length > _MAX_PROVIDER_VIDEO_BYTES:
            raise ValueError("VIDEO_PROVIDER_OUTPUT_SIZE_INVALID")
        if source.content_type != "video/mp4":
            raise ValueError("VIDEO_PROVIDER_OUTPUT_MIME_INVALID")
        checksum = _head_sha256(source.checksum_sha256_b64, source.metadata)
        try:
            probe = await self._probe(
                spec=spec,
                source_key=source_key,
                source_size=source.content_length,
                checksum=checksum,
            )
            if not probe.decode_ok:
                raise ValueError("VIDEO_PROVIDER_OUTPUT_NOT_DECODABLE")
            if probe.mime_type != "video/mp4":
                raise ValueError("VIDEO_PROVIDER_OUTPUT_MIME_INVALID")
            if probe.container.casefold() not in {"mp4", "mov,mp4,m4a,3gp,3g2,mj2"}:
                raise ValueError("VIDEO_PROVIDER_CONTAINER_UNSUPPORTED")
            shot_token = hashlib.sha256(
                f"{shot.shot.shot_id}\x00{shot.paid_operation_id}".encode("utf-8")
            ).hexdigest()
            durable_key = (
                f"generated/video/v1/{spec.organization_id}/{spec.project_id}/"
                f"shots/{shot_token}/{checksum}.mp4"
            )
            await self.object_store.copy(
                source_bucket=self.bucket,
                source_key=source_key,
                destination_bucket=self.bucket,
                destination_key=durable_key,
            )
            durable = await self.object_store.head(
                bucket=self.bucket,
                object_key=durable_key,
            )
            durable_checksum = _head_sha256(
                durable.checksum_sha256_b64,
                durable.metadata,
            )
            if durable.content_length != source.content_length or durable_checksum != checksum:
                raise RuntimeError("VIDEO_PROVIDER_OUTPUT_PROMOTION_MISMATCH")
            if durable.content_type != "video/mp4":
                raise RuntimeError("VIDEO_PROVIDER_OUTPUT_PROMOTION_MIME_MISMATCH")
            clip = StoredVideoClip(
                storage_key=durable_key,
                checksum_sha256=checksum,
                mime_type="video/mp4",
                size_bytes=durable.content_length,
                width=probe.width,
                height=probe.height,
                duration_ms=int(probe.duration_seconds * Decimal("1000")),
                durable_asset_ref=durable_key,
                poster_frame_ref=probe.poster_frame_ref,
                tail_frame_ref=probe.tail_frame_ref,
                keyframe_refs=probe.keyframe_refs,
            )
            return clip, probe
        finally:
            try:
                await self.object_store.delete_candidate(
                    bucket=self.bucket,
                    object_key=source_key,
                )
            except Exception:
                pass

    async def _probe(
        self,
        *,
        spec: VideoTaskSpec,
        source_key: str,
        source_size: int,
        checksum: str,
    ) -> VideoProbeResult:
        scope = hashlib.sha256(
            f"{spec.organization_id}\x00{spec.task_id}\x00{source_key}".encode("utf-8")
        ).hexdigest()
        exchange_key = (
            f"sandbox-exchange/v1/{spec.organization_id}/{scope}/probe/{checksum}.mp4"
        )
        await self.object_store.copy(
            source_bucket=self.bucket,
            source_key=source_key,
            destination_bucket=self.exchange_bucket,
            destination_key=exchange_key,
        )
        try:
            staged = await self.object_store.head(
                bucket=self.exchange_bucket,
                object_key=exchange_key,
            )
            if staged.content_length != source_size:
                raise RuntimeError("VIDEO_PROBE_STAGE_SIZE_MISMATCH")
            if _head_sha256(staged.checksum_sha256_b64, staged.metadata) != checksum:
                raise RuntimeError("VIDEO_PROBE_STAGE_CHECKSUM_MISMATCH")
            payload = {
                "organization_id": spec.organization_id,
                "agent_run_id": spec.task_id,
                "command": [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=format_name,duration:stream=codec_type,codec_name,width,height,r_frame_rate",
                    "-of",
                    "json",
                    "/sandbox/input/provider.mp4",
                ],
                "timeout_seconds": 120,
                "exchange_inputs": [
                    {
                        "exchange_key": exchange_key,
                        "path": "input/provider.mp4",
                        "max_bytes": source_size,
                        "expected_sha256": checksum,
                    }
                ],
                "exchange_outputs": [],
            }
            response = await asyncio.to_thread(
                _sandbox_request,
                base_url=self.sandbox_base_url,
                auth_secret=self.sandbox_auth_secret,
                timeout_seconds=self.sandbox_timeout_seconds,
                payload=payload,
            )
            if response["exit_code"] != 0:
                raise ValueError("VIDEO_PROVIDER_FFPROBE_FAILED")
            stdout = response.get("stdout")
            if not isinstance(stdout, str) or len(stdout) > 1024 * 1024:
                raise ValueError("VIDEO_PROVIDER_FFPROBE_OUTPUT_INVALID")
            return _decode_ffprobe(stdout)
        finally:
            try:
                await self.object_store.delete_candidate(
                    bucket=self.exchange_bucket,
                    object_key=exchange_key,
                )
            except Exception:
                pass


class HostedVideoMediaSandbox:
    """NODE-48 media composer bound to the remote, network-disabled sandbox runtime."""

    def __init__(self, runtime: SandboxExchangeMediaRuntime) -> None:
        self.runtime = runtime
        self.typed = TypedFfmpegSandbox(executor=runtime, resolver=runtime)

    @classmethod
    def from_spec(cls, spec: VideoTaskSpec) -> HostedVideoMediaSandbox:
        return cls(
            SandboxExchangeMediaRuntime.from_env(
                organization_id=spec.organization_id,
                project_id=spec.project_id,
                task_id=spec.task_id,
                operation_id=spec.operation_id,
            )
        )

    async def render(self, timeline: VideoTimeline) -> RenderedVideo:
        return await self.typed.render(timeline)


class PostgresVideoCostObserver:
    """Verify NODE-27's paid-model ledger; never create a second provider charge."""

    def __init__(self, database_dsn: str) -> None:
        self.dsn = _asyncpg_dsn(database_dsn)

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
        del video_job_id, shot_id
        connection = await asyncpg.connect(self.dsn)
        try:
            rows = await connection.fetch(
                """
                SELECT cl.amount, cl.confidence, cl.pricing_snapshot_id,
                       cl.external_provider_request_id
                FROM cost_ledger cl
                JOIN idempotency_operations io ON io.id = cl.operation_id
                WHERE io.operation_type = 'paid_model_invocation'
                  AND io.business_scope_id = $1
                  AND cl.entry_type = 'actual_cost'
                  AND cl.cost_basis = 'provider_cost'
                  AND cl.provider = $2
                  AND cl.model = $3
                ORDER BY cl.occurred_at, cl.id
                LIMIT 2
                """,
                UUID(paid_operation_id),
                provider,
                model,
            )
            if len(rows) != 1:
                raise RuntimeError("VIDEO_COST_LEDGER_ENTRY_NOT_UNIQUE")
            row = rows[0]
            if provider_request_id and row["external_provider_request_id"] != provider_request_id:
                raise RuntimeError("VIDEO_COST_PROVIDER_REQUEST_MISMATCH")
            if amount_usd is not None and Decimal(row["amount"]) != amount_usd:
                raise RuntimeError("VIDEO_COST_AMOUNT_MISMATCH")
            if str(row["confidence"]) != confidence.casefold():
                raise RuntimeError("VIDEO_COST_CONFIDENCE_MISMATCH")
            if pricing_snapshot_id is not None and row["pricing_snapshot_id"] != pricing_snapshot_id:
                raise RuntimeError("VIDEO_COST_PRICE_SNAPSHOT_MISMATCH")
            return True
        finally:
            await connection.close()


class PostgresVideoEventSink:
    """Append idempotent NODE-48 events to the canonical domain outbox."""

    def __init__(self, database_dsn: str) -> None:
        self.dsn = _asyncpg_dsn(database_dsn)

    async def emit(
        self,
        event_type: str,
        *,
        organization_id: str,
        video_job_id: str,
        payload: Mapping[str, object],
    ) -> None:
        if not event_type.startswith("video_generation.") or len(event_type) > 150:
            raise ValueError("VIDEO_EVENT_TYPE_INVALID")
        normalized = _json_value(dict(payload))
        if not isinstance(normalized, dict):
            raise ValueError("VIDEO_EVENT_PAYLOAD_INVALID")
        aggregate_id = uuid5(UUID(organization_id), video_job_id)
        event_payload = {
            "video_job_id": video_job_id,
            **normalized,
        }
        digest = hashlib.sha256(
            json.dumps(
                event_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        event_id = uuid5(
            aggregate_id,
            f"node48:{event_type}:{digest}",
        )
        connection = await asyncpg.connect(self.dsn)
        try:
            await connection.execute(
                """
                INSERT INTO outbox_events (
                    id, organization_id, event_name, aggregate_type, aggregate_id,
                    schema_version, payload_json, published_at, publish_attempts,
                    created_at
                ) VALUES (
                    $1,$2,$3,'video_generation',$4,1,$5::jsonb,NULL,0,now()
                )
                ON CONFLICT (id) DO NOTHING
                """,
                event_id,
                UUID(organization_id),
                event_type,
                aggregate_id,
                json.dumps(
                    event_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        finally:
            await connection.close()


class HostedVideoValidator(CompositeVideoValidator):
    """Production V1 technical validator.

    Identity/brand validation is intentionally not fabricated. Hosted V1 rejects
    specs requesting those controls before pipeline execution, so this validator is
    only used for technical/safety/final geometry checks.
    """


def _provider_output_key(value: str, *, bucket: str) -> str:
    prefix = f"s3://{bucket}/"
    if not value.startswith(prefix):
        raise ValueError("VIDEO_PROVIDER_OUTPUT_BUCKET_MISMATCH")
    key = value[len(prefix) :]
    if (
        not key.startswith("provider-output/v1/async/")
        or len(key) > 1024
        or "\x00" in key
        or "\n" in key
        or "\r" in key
        or "//" in key
        or "/../" in key
        or key.endswith("/..")
        or not key.endswith(".mp4")
    ):
        raise ValueError("VIDEO_PROVIDER_OUTPUT_REF_INVALID")
    return key


def _head_sha256(checksum_b64: str | None, metadata: Mapping[str, str]) -> str:
    metadata_checksum = metadata.get("sha256") or metadata.get("lumi-checksum-sha256")
    if metadata_checksum is not None:
        value = metadata_checksum.lower()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise RuntimeError("VIDEO_OUTPUT_SHA256_METADATA_INVALID")
        return value
    if checksum_b64:
        try:
            raw = base64.b64decode(checksum_b64, validate=True)
        except Exception as exc:
            raise RuntimeError("VIDEO_OUTPUT_SHA256_HEADER_INVALID") from exc
        if len(raw) != 32:
            raise RuntimeError("VIDEO_OUTPUT_SHA256_HEADER_INVALID")
        return raw.hex()
    raise RuntimeError("VIDEO_OUTPUT_SHA256_REQUIRED")


def _sandbox_request(
    *,
    base_url: str,
    auth_secret: str,
    timeout_seconds: float,
    payload: dict[str, object],
) -> dict[str, Any]:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(body) > 64 * 1024:
        raise RuntimeError("VIDEO_SANDBOX_REQUEST_TOO_LARGE")
    timestamp = int(time.time())
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{_CALLER}\n{timestamp}\nPOST\n{_EXECUTE_PATH}\n{body_hash}".encode("utf-8")
    signature = hmac.new(
        auth_secret.encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()
    request = urllib.request.Request(
        f"{base_url}{_EXECUTE_PATH}",
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
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = int(response.status)
            raw = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise RuntimeError("VIDEO_SANDBOX_RESPONSE_TOO_LARGE")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("VIDEO_SANDBOX_RESPONSE_INVALID") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("VIDEO_SANDBOX_RESPONSE_INVALID")
    if not 200 <= status < 300:
        code = decoded.get("code")
        raise RuntimeError(code if isinstance(code, str) and code else "VIDEO_SANDBOX_HTTP_ERROR")
    exit_code = decoded.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise RuntimeError("VIDEO_SANDBOX_EXIT_CODE_INVALID")
    return decoded


def _decode_ffprobe(raw: str) -> VideoProbeResult:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("VIDEO_FFPROBE_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("VIDEO_FFPROBE_JSON_INVALID")
    streams = payload.get("streams")
    format_payload = payload.get("format")
    if not isinstance(streams, list) or not isinstance(format_payload, dict):
        raise ValueError("VIDEO_FFPROBE_FIELDS_INVALID")
    video_streams = [
        item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"
    ]
    if len(video_streams) != 1:
        raise ValueError("VIDEO_FFPROBE_VIDEO_STREAM_INVALID")
    video = video_streams[0]
    width = _positive_int(video.get("width"), "VIDEO_FFPROBE_WIDTH_INVALID")
    height = _positive_int(video.get("height"), "VIDEO_FFPROBE_HEIGHT_INVALID")
    codec = _required_text(video.get("codec_name"), "VIDEO_FFPROBE_CODEC_INVALID")
    fps = _rational_decimal(video.get("r_frame_rate"))
    duration = _positive_decimal(format_payload.get("duration"), "VIDEO_FFPROBE_DURATION_INVALID")
    container = _required_text(format_payload.get("format_name"), "VIDEO_FFPROBE_CONTAINER_INVALID")
    return VideoProbeResult(
        decode_ok=True,
        mime_type="video/mp4",
        container=container,
        video_codec=codec,
        width=width,
        height=height,
        fps=fps,
        duration_seconds=duration,
        keyframe_refs=(),
        poster_frame_ref=None,
        tail_frame_ref=None,
        has_audio=any(
            isinstance(item, dict) and item.get("codec_type") == "audio" for item in streams
        ),
    )


def _rational_decimal(value: object) -> Decimal:
    text = _required_text(value, "VIDEO_FFPROBE_FPS_INVALID")
    try:
        numerator_text, denominator_text = text.split("/", 1)
        numerator = Decimal(numerator_text)
        denominator = Decimal(denominator_text)
    except (ValueError, InvalidOperation) as exc:
        raise ValueError("VIDEO_FFPROBE_FPS_INVALID") from exc
    if denominator == 0:
        raise ValueError("VIDEO_FFPROBE_FPS_INVALID")
    result = numerator / denominator
    if not result.is_finite() or result <= 0:
        raise ValueError("VIDEO_FFPROBE_FPS_INVALID")
    return result


def _positive_decimal(value: object, code: str) -> Decimal:
    if isinstance(value, float):
        raise ValueError(code)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(code) from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(code)
    return result


def _positive_int(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(code)
    return value


def _required_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError(code)
    return value


def _json_value(value: object, *, depth: int = 0) -> object:
    if depth > 16:
        raise ValueError("VIDEO_EVENT_PAYLOAD_TOO_DEEP")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("VIDEO_EVENT_NON_FINITE_FLOAT")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("VIDEO_EVENT_NON_FINITE_DECIMAL")
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("VIDEO_EVENT_KEY_INVALID")
        return {
            key: _json_value(child, depth=depth + 1)
            for key, child in sorted(value.items())
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(child, depth=depth + 1) for child in value]
    raise ValueError(f"VIDEO_EVENT_VALUE_INVALID:{type(value).__name__}")


def _required_env(name: str, *, max_length: int = 4096) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _env_bool(name: str) -> bool:
    value = os.getenv(name, "").strip().casefold()
    if value in {"", "0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError(f"{name}_INVALID")


def _asyncpg_dsn(database_dsn: str) -> str:
    if database_dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_dsn[len("postgresql+asyncpg://") :]
    if database_dsn.startswith("postgresql://"):
        return database_dsn
    raise ValueError("VIDEO_DATABASE_URL_MUST_USE_POSTGRESQL")


__all__ = [
    "HostedVideoMediaSandbox",
    "HostedVideoOutputAdapter",
    "HostedVideoValidator",
    "PostgresVideoCostObserver",
    "PostgresVideoEventSink",
]
