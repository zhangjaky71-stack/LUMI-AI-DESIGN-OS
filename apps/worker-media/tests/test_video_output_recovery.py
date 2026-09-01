from __future__ import annotations

import asyncio

import pytest

from lumi_worker_media.video_output_recovery import DeferredProviderOutputStore


class _Delegate:
    def __init__(self, *, fail_provider_delete: bool = False) -> None:
        self.deleted: list[tuple[str, str]] = []
        self.fail_provider_delete = fail_provider_delete

    async def head(self, *, bucket: str, object_key: str) -> tuple[str, str]:
        return bucket, object_key

    async def copy(
        self,
        *,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> None:
        del source_bucket, source_key, destination_bucket, destination_key

    async def delete_candidate(self, *, bucket: str, object_key: str) -> None:
        if self.fail_provider_delete and object_key.startswith("provider-output/v1/async/"):
            raise RuntimeError("s3 delete unavailable")
        self.deleted.append((bucket, object_key))


def test_provider_output_delete_is_deferred_but_exchange_cleanup_is_immediate() -> None:
    async def run() -> None:
        delegate = _Delegate()
        store = DeferredProviderOutputStore(delegate)  # type: ignore[arg-type]
        provider = "provider-output/v1/async/a/b/c/video.mp4"
        exchange = "sandbox-exchange/v1/a/b/probe/video.mp4"

        await store.delete_candidate(bucket="assets", object_key=provider)
        assert store.pending_provider_delete_count == 1
        assert delegate.deleted == []

        await store.delete_candidate(bucket="sandbox", object_key=exchange)
        assert delegate.deleted == [("sandbox", exchange)]
        assert store.pending_provider_delete_count == 1

        deleted = await store.cleanup_committed_provider_outputs()
        assert deleted == (("assets", provider),)
        assert delegate.deleted[-1] == ("assets", provider)
        assert store.pending_provider_delete_count == 0

    asyncio.run(run())


def test_provider_cleanup_failure_is_nonfatal_and_left_for_lifecycle_fallback() -> None:
    async def run() -> None:
        delegate = _Delegate(fail_provider_delete=True)
        store = DeferredProviderOutputStore(delegate)  # type: ignore[arg-type]
        provider = "provider-output/v1/async/a/b/c/video.mp4"
        await store.delete_candidate(bucket="assets", object_key=provider)

        assert await store.cleanup_committed_provider_outputs() == ()
        assert store.pending_provider_delete_count == 1
        assert delegate.deleted == []

    asyncio.run(run())


def test_non_provider_delete_failure_remains_fail_closed() -> None:
    class FailingDelegate(_Delegate):
        async def delete_candidate(self, *, bucket: str, object_key: str) -> None:
            del bucket, object_key
            raise RuntimeError("sandbox delete rejected")

    async def run() -> None:
        store = DeferredProviderOutputStore(FailingDelegate())  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="sandbox delete rejected"):
            await store.delete_candidate(
                bucket="sandbox",
                object_key="sandbox-exchange/v1/a/b/probe/video.mp4",
            )

    asyncio.run(run())
