from __future__ import annotations

import base64
import hashlib
import unittest
from dataclasses import replace
from uuid import uuid4

from lumi_asset_storage.models import ObjectHead

from lumi_tool_gateway.errors import ToolResultOffloadUnavailableError
from lumi_tool_gateway.result_offload import S3ResultOffloader


class _FakeStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail = False
        self.head_override: ObjectHead | None = None

    async def put_bytes(
        self,
        *,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
        max_bytes: int,
        metadata: dict[str, str] | None = None,
    ) -> ObjectHead:
        if self.fail:
            raise RuntimeError("s3 unavailable")
        metadata_value = dict(metadata or {})
        self.calls.append(
            {
                "bucket": bucket,
                "object_key": object_key,
                "data": data,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "metadata": metadata_value,
            }
        )
        if self.head_override is not None:
            return self.head_override
        checksum = base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")
        return ObjectHead(
            bucket=bucket,
            object_key=object_key,
            content_length=len(data),
            content_type=content_type,
            checksum_sha256_b64=checksum,
            etag="etag",
            metadata=metadata_value,
        )


class S3ResultOffloaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_deterministic_private_ref_and_metadata(self) -> None:
        store = _FakeStore()
        offloader = S3ResultOffloader(
            store=store,
            bucket="lumi-staging-exports",
            max_bytes=1024 * 1024,
        )
        organization_id = str(uuid4())
        tool_call_id = str(uuid4())
        payload = b'{"items":[1,2,3]}'
        digest = hashlib.sha256(payload).hexdigest()

        first = await offloader.store(
            organization_id=organization_id,
            tool_call_id=tool_call_id,
            resolved_tool="project.query@1.0.0",
            payload=payload,
        )
        second = await offloader.store(
            organization_id=organization_id,
            tool_call_id=tool_call_id,
            resolved_tool="project.query@1.0.0",
            payload=payload,
        )

        expected_key = f"tool-results/v1/{organization_id}/{tool_call_id}/{digest}.json"
        expected_ref = f"s3ref://lumi-staging-exports/{expected_key}#sha256={digest}"
        self.assertEqual(first, expected_ref)
        self.assertEqual(second, expected_ref)
        self.assertEqual(len(store.calls), 2)
        call = store.calls[0]
        self.assertEqual(call["object_key"], expected_key)
        self.assertEqual(call["content_type"], "application/json")
        metadata = call["metadata"]
        self.assertIsInstance(metadata, dict)
        self.assertEqual(metadata["sha256"], digest)
        self.assertEqual(metadata["schema-version"], "1")
        self.assertEqual(len(metadata["tool-sha256"]), 64)
        self.assertNotIn("http://", first)
        self.assertNotIn("https://", first)

    async def test_oversize_and_invalid_identity_never_touch_store(self) -> None:
        store = _FakeStore()
        offloader = S3ResultOffloader(
            store=store,
            bucket="lumi-exports",
            max_bytes=64 * 1024,
        )
        with self.assertRaises(ToolResultOffloadUnavailableError):
            await offloader.store(
                organization_id=str(uuid4()),
                tool_call_id=str(uuid4()),
                resolved_tool="project.query@1.0.0",
                payload=b"x" * (64 * 1024 + 1),
            )
        with self.assertRaises(ToolResultOffloadUnavailableError):
            await offloader.store(
                organization_id="not-a-uuid",
                tool_call_id=str(uuid4()),
                resolved_tool="project.query@1.0.0",
                payload=b"{}",
            )
        self.assertEqual(store.calls, [])

    async def test_wrong_object_identity_length_checksum_or_metadata_fails_closed(self) -> None:
        payload = b'{"large":true}'
        organization_id = str(uuid4())
        tool_call_id = str(uuid4())
        digest = hashlib.sha256(payload).hexdigest()
        expected_key = f"tool-results/v1/{organization_id}/{tool_call_id}/{digest}.json"
        checksum = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii")
        base_head = ObjectHead(
            bucket="lumi-exports",
            object_key=expected_key,
            content_length=len(payload),
            content_type="application/json",
            checksum_sha256_b64=checksum,
            etag="etag",
            metadata={"sha256": digest},
        )
        variants = (
            replace(base_head, bucket="wrong-bucket"),
            replace(base_head, object_key="wrong-key"),
            replace(base_head, content_length=len(payload) + 1),
            replace(base_head, checksum_sha256_b64="wrong-checksum"),
            replace(base_head, metadata={"sha256": "wrong-digest"}),
        )
        for head in variants:
            store = _FakeStore()
            store.head_override = head
            offloader = S3ResultOffloader(
                store=store,
                bucket="lumi-exports",
                max_bytes=1024 * 1024,
            )
            with self.subTest(head=head):
                with self.assertRaises(ToolResultOffloadUnavailableError):
                    await offloader.store(
                        organization_id=organization_id,
                        tool_call_id=tool_call_id,
                        resolved_tool="project.query@1.0.0",
                        payload=payload,
                    )

    async def test_storage_exception_is_normalized(self) -> None:
        store = _FakeStore()
        store.fail = True
        offloader = S3ResultOffloader(
            store=store,
            bucket="lumi-exports",
            max_bytes=1024 * 1024,
        )
        with self.assertRaisesRegex(
            ToolResultOffloadUnavailableError,
            "durable Tool Gateway result storage is unavailable",
        ):
            await offloader.store(
                organization_id=str(uuid4()),
                tool_call_id=str(uuid4()),
                resolved_tool="asset.get-metadata@1.0.0",
                payload=b"{}",
            )

    def test_constructor_rejects_invalid_bucket_and_size(self) -> None:
        store = _FakeStore()
        with self.assertRaisesRegex(ValueError, "TOOL_RESULT_BUCKET_INVALID"):
            S3ResultOffloader(store=store, bucket="", max_bytes=1024 * 1024)
        with self.assertRaisesRegex(ValueError, "TOOL_RESULT_MAX_BYTES_INVALID"):
            S3ResultOffloader(store=store, bucket="lumi-exports", max_bytes=1024)


if __name__ == "__main__":
    unittest.main()
