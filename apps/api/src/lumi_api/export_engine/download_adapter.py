from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from lumi_export_engine import DownloadGrant, DownloadPackage, ExportJob


class ObjectDownloadSigner(Protocol):
    async def presign_get(
        self,
        *,
        bucket: str,
        storage_key: str,
        filename: str,
        ttl_seconds: int,
    ) -> str: ...


class ShortLivedDownloadGrantAdapter:
    """Signed URLs are returned to the caller only and are never persisted here."""

    def __init__(self, signer: ObjectDownloadSigner) -> None:
        self.signer = signer

    async def issue(
        self,
        *,
        job: ExportJob,
        actor_id: str,
        package: DownloadPackage,
        ttl_seconds: int,
    ) -> DownloadGrant:
        if ttl_seconds < 60 or ttl_seconds > 3600:
            raise ValueError("EXPORT_DOWNLOAD_TTL_OUT_OF_RANGE")
        url = await self.signer.presign_get(
            bucket=package.bucket,
            storage_key=package.storage_key,
            filename=package.filename,
            ttl_seconds=ttl_seconds,
        )
        return DownloadGrant(
            grant_id=str(uuid4()),
            package_id=package.package_id,
            actor_id=actor_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            url=url,
        )
