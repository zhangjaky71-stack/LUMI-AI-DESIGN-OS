from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from lumi_asset_storage.s3 import S3ObjectStore
from lumi_model_gateway import ModelRequest

_MAX_IMAGE_BYTES = 100 * 1024 * 1024
_MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
_ALLOWED_IMAGE_MEDIA = {
    ("image/png", "png"),
    ("image/jpeg", "jpeg"),
    ("image/webp", "webp"),
}
_ALLOWED_FILE_MEDIA = {("video/mp4", "mp4")}
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,511}$")


class ProviderOutputStoreError(RuntimeError):
    code = "PROVIDER_OUTPUT_STORE_INVALID"


@dataclass(slots=True)
class S3ProviderOutputStore:
    object_store: S3ObjectStore
    bucket: str
    max_image_bytes: int = _MAX_IMAGE_BYTES
    max_video_bytes: int = _MAX_VIDEO_BYTES

    def __post_init__(self) -> None:
        if not _BUCKET.fullmatch(self.bucket):
            raise ProviderOutputStoreError("provider output bucket is invalid")
        if not 1 <= self.max_image_bytes <= _MAX_IMAGE_BYTES:
            raise ProviderOutputStoreError("provider output image byte limit is invalid")
        if not 1 <= self.max_video_bytes <= _MAX_VIDEO_BYTES:
            raise ProviderOutputStoreError("provider output video byte limit is invalid")

    @classmethod
    def from_env(cls) -> S3ProviderOutputStore:
        bucket = os.getenv("LUMI_PROVIDER_OUTPUT_BUCKET", "")
        region = os.getenv("LUMI_S3_REGION") or os.getenv("AWS_REGION") or ""
        if not bucket:
            raise ProviderOutputStoreError("LUMI_PROVIDER_OUTPUT_BUCKET is required")
        if not region:
            raise ProviderOutputStoreError("LUMI_S3_REGION/AWS_REGION is required")
        force_path_style = os.getenv("LUMI_S3_FORCE_PATH_STYLE", "").strip().lower()
        if force_path_style not in {"", "0", "1", "false", "true"}:
            raise ProviderOutputStoreError("LUMI_S3_FORCE_PATH_STYLE is invalid")
        return cls(
            object_store=S3ObjectStore(
                endpoint_url=os.getenv("LUMI_S3_ENDPOINT_URL") or None,
                region_name=region,
                access_key_id=os.getenv("LUMI_S3_ACCESS_KEY_ID") or None,
                secret_access_key=os.getenv("LUMI_S3_SECRET_ACCESS_KEY") or None,
                force_path_style=force_path_style in {"1", "true"},
            ),
            bucket=bucket,
        )

    async def store_bytes(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        data: bytes,
        content_type: str,
        extension: str,
    ) -> str:
        normalized_extension = extension.strip().lower()
        if (content_type, normalized_extension) not in _ALLOWED_IMAGE_MEDIA:
            raise ProviderOutputStoreError(
                "provider output byte media type is not allowed"
            )
        _validate_identity(provider=provider, model=model)
        digest = hashlib.sha256(data).hexdigest()
        object_key = (
            "provider-output/v1/"
            f"{request.organization_id}/{request.operation_id}/{digest}.{normalized_extension}"
        )
        await self.object_store.put_bytes(
            bucket=self.bucket,
            object_key=object_key,
            data=data,
            content_type=content_type,
            max_bytes=self.max_image_bytes,
            metadata=_request_metadata(
                request=request,
                provider=provider,
                model=model,
            ),
        )
        return f"s3://{self.bucket}/{object_key}"

    async def store_path(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        path: Path,
        content_type: str,
        extension: str,
        max_bytes: int,
    ) -> str:
        _validate_file_input(
            path=path,
            content_type=content_type,
            extension=extension,
            max_bytes=max_bytes,
            configured_max=self.max_video_bytes,
        )
        _validate_identity(provider=provider, model=model)
        digest = _sha256_path(path, max_bytes=max_bytes)
        normalized_extension = extension.strip().lower()
        object_key = (
            "provider-output/v1/"
            f"{request.organization_id}/{request.operation_id}/{digest}.{normalized_extension}"
        )
        await self.object_store.upload_from_path(
            bucket=self.bucket,
            object_key=object_key,
            path=path,
            content_type=content_type,
            max_bytes=max_bytes,
            metadata=_request_metadata(
                request=request,
                provider=provider,
                model=model,
            ),
        )
        return f"s3://{self.bucket}/{object_key}"

    async def store_async_path(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
        path: Path,
        content_type: str,
        extension: str,
        max_bytes: int,
    ) -> str:
        _validate_file_input(
            path=path,
            content_type=content_type,
            extension=extension,
            max_bytes=max_bytes,
            configured_max=self.max_video_bytes,
        )
        _validate_identity(provider=provider, model=model)
        if not _SAFE_ID.fullmatch(provider_request_id):
            raise ProviderOutputStoreError(
                "provider output async request identity is invalid"
            )
        digest = _sha256_path(path, max_bytes=max_bytes)
        normalized_extension = extension.strip().lower()
        request_hash = hashlib.sha256(provider_request_id.encode("utf-8")).hexdigest()[:32]
        object_key = (
            "provider-output/v1/async/"
            f"{_path_component(provider)}/{_path_component(model)}/{request_hash}/"
            f"{digest}.{normalized_extension}"
        )
        await self.object_store.upload_from_path(
            bucket=self.bucket,
            object_key=object_key,
            path=path,
            content_type=content_type,
            max_bytes=max_bytes,
            metadata={
                "lumi-kind": "provider-output",
                "lumi-provider": _metadata_value(provider, 100),
                "lumi-model": _metadata_value(model, 255),
                "lumi-provider-request-id": _metadata_value(provider_request_id, 512),
            },
        )
        return f"s3://{self.bucket}/{object_key}"


def _validate_file_input(
    *,
    path: Path,
    content_type: str,
    extension: str,
    max_bytes: int,
    configured_max: int,
) -> None:
    normalized_extension = extension.strip().lower()
    if (content_type, normalized_extension) not in _ALLOWED_FILE_MEDIA:
        raise ProviderOutputStoreError(
            "provider output file media type is not allowed"
        )
    if not 1 <= max_bytes <= configured_max:
        raise ProviderOutputStoreError("provider output file byte limit is invalid")
    if not path.is_file():
        raise ProviderOutputStoreError("provider output file is missing")
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise ProviderOutputStoreError("provider output file size is invalid")


def _request_metadata(
    *,
    request: ModelRequest,
    provider: str,
    model: str,
) -> dict[str, str]:
    return {
        "lumi-kind": "provider-output",
        "lumi-provider": _metadata_value(provider, 100),
        "lumi-model": _metadata_value(model, 255),
        "lumi-operation-id": str(request.operation_id),
    }


def _validate_identity(*, provider: str, model: str) -> None:
    if not provider or len(provider) > 100 or "\x00" in provider:
        raise ProviderOutputStoreError("provider output provider identity is invalid")
    if not model or len(model) > 255 or "\x00" in model:
        raise ProviderOutputStoreError("provider output model identity is invalid")


def _sha256_path(path: Path, *, max_bytes: int) -> str:
    digest = hashlib.sha256()
    seen = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            seen += len(chunk)
            if seen > max_bytes:
                raise ProviderOutputStoreError("provider output file exceeds byte limit")
            digest.update(chunk)
    if seen <= 0:
        raise ProviderOutputStoreError("provider output file is empty")
    return digest.hexdigest()


def _path_component(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return digest


def _metadata_value(value: str, max_length: int) -> str:
    cleaned = value.encode("ascii", "replace").decode("ascii").strip()
    if not cleaned or len(cleaned) > max_length:
        raise ProviderOutputStoreError("provider output metadata is invalid")
    return cleaned
