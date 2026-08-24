from __future__ import annotations

import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import cast
from uuid import uuid4

from lumi_api.provider_output_store import (
    ProviderOutputStoreError,
    S3ProviderOutputStore,
)
from lumi_model_gateway import Capability, ModelRequest


class FakeObjectStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.file_calls: list[dict[str, object]] = []

    async def put_bytes(
        self,
        *,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
        max_bytes: int,
        metadata: dict[str, str] | None = None,
    ) -> object:
        self.calls.append(
            {
                "bucket": bucket,
                "object_key": object_key,
                "data": data,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "metadata": metadata,
            }
        )
        return object()

    async def upload_from_path(
        self,
        *,
        bucket: str,
        object_key: str,
        path: str,
        content_type: str,
        checksum_sha256_b64: str,
    ) -> object:
        self.file_calls.append(
            {
                "bucket": bucket,
                "object_key": object_key,
                "path": path,
                "content_type": content_type,
                "checksum_sha256_b64": checksum_sha256_b64,
            }
        )
        return object()


class ProviderOutputStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_ref_is_opaque_deterministic_and_contains_no_provider_text(self) -> None:
        object_store = FakeObjectStore()
        store = S3ProviderOutputStore(
            object_store=object_store,
            bucket="lumi-assets-test",
        )
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.IMAGE_GENERATE,
            inputs={"prompt": "private customer prompt"},
        )
        first = await store.store_bytes(
            request=request,
            provider="openai",
            model="gpt-image-test",
            data=b"same-image",
            content_type="image/png",
            extension="png",
        )
        second = await store.store_bytes(
            request=request,
            provider="openai",
            model="gpt-image-test",
            data=b"same-image",
            content_type="image/png",
            extension="png",
        )
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("s3://lumi-assets-test/provider-output/v1/"))
        self.assertNotIn("openai", first)
        self.assertNotIn("gpt-image", first)
        self.assertNotIn("private", first)
        call = object_store.calls[0]
        self.assertEqual(call["max_bytes"], 100 * 1024 * 1024)
        self.assertEqual(call["content_type"], "image/png")
        metadata = cast(dict[str, str], call["metadata"])
        self.assertEqual(metadata["lumi-kind"], "provider-output")

    async def test_async_video_path_uses_existing_s3_checksum_contract(self) -> None:
        object_store = FakeObjectStore()
        store = S3ProviderOutputStore(
            object_store=object_store,
            bucket="lumi-assets-test",
        )
        payload = b"fake-mp4-payload"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "provider.mp4"
            path.write_bytes(payload)
            ref = await store.store_async_path(
                provider="openai",
                model="sora-2",
                provider_request_id="video_job_123",
                path=path,
                content_type="video/mp4",
                extension="mp4",
                max_bytes=1024,
            )

        digest = hashlib.sha256(payload).hexdigest()
        expected_b64 = base64.b64encode(bytes.fromhex(digest)).decode("ascii")
        self.assertTrue(ref.startswith("s3://lumi-assets-test/provider-output/v1/async/"))
        self.assertTrue(ref.endswith(f"/{digest}.mp4"))
        self.assertEqual(len(object_store.file_calls), 1)
        call = object_store.file_calls[0]
        self.assertEqual(call["content_type"], "video/mp4")
        self.assertEqual(call["checksum_sha256_b64"], expected_b64)
        self.assertIsInstance(call["path"], str)
        self.assertNotIn("max_bytes", call)
        self.assertNotIn("metadata", call)

    async def test_video_path_size_bound_fails_before_s3_upload(self) -> None:
        object_store = FakeObjectStore()
        store = S3ProviderOutputStore(
            object_store=object_store,
            bucket="lumi-assets-test",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "provider.mp4"
            path.write_bytes(b"12345")
            with self.assertRaises(ProviderOutputStoreError):
                await store.store_async_path(
                    provider="openai",
                    model="sora-2",
                    provider_request_id="video_job_123",
                    path=path,
                    content_type="video/mp4",
                    extension="mp4",
                    max_bytes=4,
                )
        self.assertEqual(object_store.file_calls, [])

    async def test_non_image_media_is_rejected_before_object_store(self) -> None:
        object_store = FakeObjectStore()
        store = S3ProviderOutputStore(
            object_store=object_store,
            bucket="lumi-assets-test",
        )
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.IMAGE_GENERATE,
            inputs={"prompt": "x"},
        )
        with self.assertRaises(ProviderOutputStoreError):
            await store.store_bytes(
                request=request,
                provider="openai",
                model="gpt-image-test",
                data=b"video",
                content_type="video/mp4",
                extension="mp4",
            )
        self.assertEqual(object_store.calls, [])

    def test_invalid_bucket_fails_closed(self) -> None:
        with self.assertRaises(ProviderOutputStoreError):
            S3ProviderOutputStore(
                object_store=FakeObjectStore(),
                bucket="INVALID_BUCKET_NAME",
            )


if __name__ == "__main__":
    unittest.main()
