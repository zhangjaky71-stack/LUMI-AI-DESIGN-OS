from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_model_gateway import Capability, ModelRequest

from lumi_api.provider_output_store import (
    ProviderOutputStoreError,
    S3ProviderOutputStore,
)


class FakeObjectStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def put_bytes(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        return object()


class ProviderOutputStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_ref_is_opaque_deterministic_and_contains_no_provider_text(self) -> None:
        object_store = FakeObjectStore()
        store = S3ProviderOutputStore(  # type: ignore[arg-type]
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
        self.assertEqual(call["metadata"]["lumi-kind"], "provider-output")

    async def test_non_image_media_is_rejected_before_object_store(self) -> None:
        object_store = FakeObjectStore()
        store = S3ProviderOutputStore(  # type: ignore[arg-type]
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
            S3ProviderOutputStore(  # type: ignore[arg-type]
                object_store=FakeObjectStore(),
                bucket="INVALID_BUCKET_NAME",
            )


if __name__ == "__main__":
    unittest.main()
