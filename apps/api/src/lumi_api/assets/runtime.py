from __future__ import annotations

from dataclasses import dataclass

from lumi_asset_storage.models import ObjectStore
from lumi_asset_storage.s3 import S3ObjectStore
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.config import Settings


@dataclass(frozen=True, slots=True)
class AssetStorageRuntime:
    session_factory: async_sessionmaker[AsyncSession]
    object_store: ObjectStore
    bucket: str
    presign_ttl_seconds: int
    download_ttl_seconds: int
    max_file_bytes: int
    max_org_storage_bytes: int
    multipart_threshold_bytes: int


def build_asset_storage_runtime(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> AssetStorageRuntime:
    if not settings.s3_bucket:
        raise RuntimeError("S3_BUCKET is required for Asset Storage")
    object_store = S3ObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key,
        force_path_style=settings.s3_force_path_style,
    )
    return AssetStorageRuntime(
        session_factory=session_factory,
        object_store=object_store,
        bucket=settings.s3_bucket,
        presign_ttl_seconds=settings.asset_presign_ttl_seconds,
        download_ttl_seconds=settings.asset_download_ttl_seconds,
        max_file_bytes=settings.asset_max_file_bytes,
        max_org_storage_bytes=settings.asset_max_org_storage_bytes,
        multipart_threshold_bytes=settings.asset_multipart_threshold_bytes,
    )
