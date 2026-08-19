from __future__ import annotations

import base64
import hashlib
import os
from typing import Protocol
from uuid import UUID

from lumi_asset_storage.models import ObjectHead
from lumi_asset_storage.s3 import S3ObjectStore

from .errors import ToolResultOffloadUnavailableError

_DEFAULT_MAX_BYTES = 16 * 1024 * 1024
_MIN_MAX_BYTES = 64 * 1024
_MAX_MAX_BYTES = 64 * 1024 * 1024
_CONTENT_TYPE = "application/json"


class ResultObjectStore(Protocol):
    async def put_bytes(
        self,
        *,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
        max_bytes: int,
        metadata: dict[str, str] | None = None,
    ) -> ObjectHead: ...


class S3ResultOffloader:
    """Durably offload large Tool Gateway results to a private KMS-backed S3 bucket."""

    def __init__(
        self,
        *,
        store: ResultObjectStore,
        bucket: str,
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        if not bucket or len(bucket) > 255 or "\x00" in bucket:
            raise ValueError("TOOL_RESULT_BUCKET_INVALID")
        if not _MIN_MAX_BYTES <= max_bytes <= _MAX_MAX_BYTES:
            raise ValueError("TOOL_RESULT_MAX_BYTES_INVALID")
        self.store = store
        self.bucket = bucket
        self.max_bytes = max_bytes

    @classmethod
    def from_env(cls) -> S3ResultOffloader:
        bucket = os.getenv("LUMI_TOOL_RESULT_BUCKET", "")
        region = os.getenv("LUMI_S3_REGION", "")
        if not region or len(region) > 64 or "\x00" in region:
            raise ValueError("LUMI_S3_REGION_REQUIRED")
        max_bytes = _env_max_bytes()
        store = S3ObjectStore(
            endpoint_url=os.getenv("LUMI_S3_ENDPOINT_URL") or None,
            region_name=region,
            access_key_id=os.getenv("AWS_ACCESS_KEY_ID") or None,
            secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY") or None,
            force_path_style=_env_bool("LUMI_S3_FORCE_PATH_STYLE", default=False),
        )
        return cls(store=store, bucket=bucket, max_bytes=max_bytes)

    async def store(
        self,
        *,
        organization_id: str,
        tool_call_id: str,
        resolved_tool: str,
        payload: bytes,
    ) -> str:
        organization = _uuid_segment(organization_id, "TOOL_RESULT_ORGANIZATION_ID_INVALID")
        tool_call = _uuid_segment(tool_call_id, "TOOL_RESULT_TOOL_CALL_ID_INVALID")
        if not resolved_tool or len(resolved_tool) > 320 or "\x00" in resolved_tool:
            raise ToolResultOffloadUnavailableError("resolved tool identity is invalid")
        if not isinstance(payload, bytes):
            raise ToolResultOffloadUnavailableError("tool result payload must be bytes")
        if len(payload) > self.max_bytes:
            raise ToolResultOffloadUnavailableError(
                f"tool result exceeds durable offload limit of {self.max_bytes} bytes"
            )

        digest = hashlib.sha256(payload).hexdigest()
        checksum_b64 = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii")
        tool_digest = hashlib.sha256(resolved_tool.encode("utf-8")).hexdigest()
        object_key = f"tool-results/v1/{organization}/{tool_call}/{digest}.json"
        metadata = {
            "sha256": digest,
            "tool-sha256": tool_digest,
            "schema-version": "1",
        }
        try:
            head = await self.store.put_bytes(
                bucket=self.bucket,
                object_key=object_key,
                data=payload,
                content_type=_CONTENT_TYPE,
                max_bytes=self.max_bytes,
                metadata=metadata,
            )
        except Exception as exc:
            raise ToolResultOffloadUnavailableError(
                "durable Tool Gateway result storage is unavailable"
            ) from exc

        if head.bucket != self.bucket or head.object_key != object_key:
            raise ToolResultOffloadUnavailableError(
                "durable Tool Gateway result storage returned the wrong object identity"
            )
        if head.content_length != len(payload):
            raise ToolResultOffloadUnavailableError(
                "durable Tool Gateway result storage length verification failed"
            )
        if head.checksum_sha256_b64 not in {None, checksum_b64}:
            raise ToolResultOffloadUnavailableError(
                "durable Tool Gateway result storage checksum verification failed"
            )
        if head.metadata.get("sha256") != digest:
            raise ToolResultOffloadUnavailableError(
                "durable Tool Gateway result storage metadata verification failed"
            )
        return f"s3ref://{self.bucket}/{object_key}#sha256={digest}"


def _uuid_segment(value: str, code: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ToolResultOffloadUnavailableError(code) from exc


def _env_max_bytes() -> int:
    raw = os.getenv("LUMI_TOOL_RESULT_MAX_BYTES", str(_DEFAULT_MAX_BYTES))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("LUMI_TOOL_RESULT_MAX_BYTES_INVALID") from exc
    if not _MIN_MAX_BYTES <= value <= _MAX_MAX_BYTES:
        raise ValueError("LUMI_TOOL_RESULT_MAX_BYTES_INVALID")
    return value


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name}_INVALID")
