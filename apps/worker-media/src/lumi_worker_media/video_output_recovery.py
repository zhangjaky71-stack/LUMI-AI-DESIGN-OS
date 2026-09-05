from __future__ import annotations

from lumi_asset_storage.models import ObjectHead
from lumi_asset_storage.s3 import S3ObjectStore

_PROVIDER_OUTPUT_PREFIX = "provider-output/v1/async/"


class DeferredProviderOutputStore:
    """Delay provider-output deletion until the Hosted video snapshot has committed.

    HostedVideoOutputAdapter deletes candidates in a finally block. Delegating those
    deletes immediately creates a crash window: the promoted clip/artifact may exist
    while the recovery snapshot is still old, leaving the next retry unable to
    materialize the same provider output. This wrapper defers only canonical async
    provider-output deletes; sandbox exchange cleanup remains immediate.
    """

    def __init__(self, delegate: S3ObjectStore) -> None:
        self.delegate = delegate
        self._pending_provider_deletes: set[tuple[str, str]] = set()

    @property
    def pending_provider_delete_count(self) -> int:
        return len(self._pending_provider_deletes)

    async def head(self, *, bucket: str, object_key: str) -> ObjectHead:
        return await self.delegate.head(bucket=bucket, object_key=object_key)

    async def copy(
        self,
        *,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> None:
        await self.delegate.copy(
            source_bucket=source_bucket,
            source_key=source_key,
            destination_bucket=destination_bucket,
            destination_key=destination_key,
        )

    async def delete_candidate(self, *, bucket: str, object_key: str) -> None:
        if object_key.startswith(_PROVIDER_OUTPUT_PREFIX):
            self._pending_provider_deletes.add((bucket, object_key))
            return
        await self.delegate.delete_candidate(bucket=bucket, object_key=object_key)

    async def cleanup_committed_provider_outputs(self) -> tuple[tuple[str, str], ...]:
        """Best-effort cleanup after DB commit; lifecycle policy is the final fallback."""

        deleted: list[tuple[str, str]] = []
        for bucket, object_key in tuple(sorted(self._pending_provider_deletes)):
            try:
                await self.delegate.delete_candidate(bucket=bucket, object_key=object_key)
            except Exception:
                continue
            self._pending_provider_deletes.discard((bucket, object_key))
            deleted.append((bucket, object_key))
        return tuple(deleted)


__all__ = ["DeferredProviderOutputStore"]
