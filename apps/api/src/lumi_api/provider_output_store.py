from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

from lumi_asset_storage.s3 import S3ObjectStore
from lumi_model_gateway import ModelRequest

_MAX_IMAGE_BYTES = 100 * 1024 * 1024
_ALLOWED_MEDIA = {
    ("image/png", "png"),
    ("image/jpeg", "jpeg"),
    ("image/webp", "webp"),
}
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


class ProviderOutputStoreError(RuntimeError):
    code = "PROVIDER_OUTPUT_STORE_INVALID"


@dataclass(slots=True)
class S3ProviderOutputStore:
    object_store: S3ObjectStore
    bucket: str
    max_image_bytes: int = _MAX_IMAGE_BYTES

    def __post_init__(self) -> None:
        if not _BUCKET.fullmatch(self.bucket):
            raise ProviderOutputStoreError("provider output bucket is invalid")
        if not 1 <= self.max_image_bytes <= _MAX_IMAGE_BYTES:
            raise ProviderOutputStoreError("provider output image byte limit is invalid")

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
        if (content_type, normalized_extension) not in _ALLOWED_MEDIA:
            raise ProviderOutputStoreError("provider output media type is not allowed")
        if not provider or len(provider) > 100 or "\x00" in provider:
            raise ProviderOutputStoreError("provider output provider identity is invalid")
        if not model or len(model) > 255 or "\x00" in model:
            raise ProviderOutputStoreError("provider output model identity is invalid")
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
            metadata={
                "lumi-kind": "provider-output",
                "lumi-provider": _metadata_value(provider, 100),
                "lumi-model": _metadata_value(model, 255),
                "lumi-operation-id": str(request.operation_id),
            },
        )
        return f"s3://{self.bucket}/{object_key}"


def _metadata_value(value: str, max_length: int) -> str:
    cleaned = value.encode("ascii", "replace").decode("ascii").strip()
    if not cleaned or len(cleaned) > max_length:
        raise ProviderOutputStoreError("provider output metadata is invalid")
    return cleaned
