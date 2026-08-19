from __future__ import annotations

import asyncio
import hashlib
import unittest
from decimal import Decimal

from lumi_image_generation.errors import ImageGenerationTransientError
from lumi_image_generation.model import ImageGenerationSpec, OutputRequirements, ValidatedImage
from lumi_worker_media.image_generation_ports import S3GeneratedImageStore


class _FakePutStore:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def put_bytes(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        return object()


def _spec() -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        task_id="33333333-3333-3333-3333-333333333333",
        operation_id="44444444-4444-4444-4444-444444444444",
        purpose="test durable image storage",
        mode="TEXT_TO_IMAGE",
        prompt_compilation_ref="prompt:test:v1",
        objective="create image",
        content="ceramic cup",
        visual_direction="minimal",
        aspect_ratio="1:1",
        target_width=1024,
        target_height=1024,
        variant_count=1,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile="BALANCED",
        budget_limit_usd=Decimal("1.00"),
        output_requirements=OutputRequirements(format="PNG"),
        code_git_sha="a" * 40,
    )


def _image() -> ValidatedImage:
    content = b"validated-png-bytes"
    return ValidatedImage(
        content=content,
        mime_type="image/png",
        width=1024,
        height=1024,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        has_alpha=False,
    )


class GeneratedImageStorageTests(unittest.TestCase):
    def test_store_writes_only_durable_generated_namespace(self) -> None:
        backend = _FakePutStore()
        store = S3GeneratedImageStore(
            bucket="lumi-assets",
            object_store=backend,  # type: ignore[arg-type]
            max_bytes=1024,
        )
        result = asyncio.run(
            store.store(
                spec=_spec(),
                candidate_id="image-candidate:test",
                image=_image(),
            )
        )
        self.assertTrue(result.storage_key.startswith("generated/v1/"))
        self.assertNotIn("provider-output/v1/", result.storage_key)
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(backend.calls[0]["bucket"], "lumi-assets")
        self.assertEqual(backend.calls[0]["object_key"], result.storage_key)

    def test_store_transport_failure_is_retryable(self) -> None:
        backend = _FakePutStore(error=RuntimeError("s3 unavailable"))
        store = S3GeneratedImageStore(
            bucket="lumi-assets",
            object_store=backend,  # type: ignore[arg-type]
        )
        with self.assertRaises(ImageGenerationTransientError) as raised:
            asyncio.run(
                store.store(
                    spec=_spec(),
                    candidate_id="image-candidate:test",
                    image=_image(),
                )
            )
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(raised.exception.code, "GENERATION_STORAGE_TEMPORARY")

    def test_store_backend_validation_failure_remains_permanent(self) -> None:
        backend = _FakePutStore(error=ValueError("S3_OBJECT_TOO_LARGE"))
        store = S3GeneratedImageStore(
            bucket="lumi-assets",
            object_store=backend,  # type: ignore[arg-type]
        )
        with self.assertRaisesRegex(ValueError, "S3_OBJECT_TOO_LARGE"):
            asyncio.run(
                store.store(
                    spec=_spec(),
                    candidate_id="image-candidate:test",
                    image=_image(),
                )
            )

    def test_store_checksum_mismatch_fails_before_io(self) -> None:
        backend = _FakePutStore()
        store = S3GeneratedImageStore(
            bucket="lumi-assets",
            object_store=backend,  # type: ignore[arg-type]
        )
        invalid = ValidatedImage(
            content=b"tampered",
            mime_type="image/png",
            width=1024,
            height=1024,
            checksum_sha256="0" * 64,
            has_alpha=False,
        )
        with self.assertRaisesRegex(ValueError, "GENERATION_STORAGE_CHECKSUM_MISMATCH"):
            asyncio.run(
                store.store(
                    spec=_spec(),
                    candidate_id="image-candidate:test",
                    image=invalid,
                )
            )
        self.assertEqual(backend.calls, [])


if __name__ == "__main__":
    unittest.main()
