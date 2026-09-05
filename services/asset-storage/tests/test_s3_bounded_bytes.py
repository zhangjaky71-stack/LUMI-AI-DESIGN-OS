from __future__ import annotations

import asyncio
import base64
import hashlib
import io
from unittest.mock import patch

import pytest

from lumi_asset_storage.s3 import S3ObjectStore


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}
        self.last_put: dict[str, object] | None = None

    def put_object(self, **kwargs: object) -> dict[str, object]:
        body = kwargs["Body"]
        assert isinstance(body, bytes)
        self.last_put = dict(kwargs)
        metadata = kwargs.get("Metadata")
        assert metadata is None or isinstance(metadata, dict)
        self.objects[(str(kwargs["Bucket"]), str(kwargs["Key"]))] = {
            "body": body,
            "content_type": kwargs.get("ContentType"),
            "checksum": kwargs.get("ChecksumSHA256"),
            "metadata": dict(metadata or {}),
        }
        return {"ETag": '"etag"'}

    def head_object(self, **kwargs: object) -> dict[str, object]:
        row = self.objects[(str(kwargs["Bucket"]), str(kwargs["Key"]))]
        body = row["body"]
        assert isinstance(body, bytes)
        return {
            "ContentLength": len(body),
            "ContentType": row["content_type"],
            "ChecksumSHA256": row["checksum"],
            "ETag": '"etag"',
            "Metadata": row["metadata"],
        }

    def get_object(self, **kwargs: object) -> dict[str, object]:
        row = self.objects[(str(kwargs["Bucket"]), str(kwargs["Key"]))]
        body = row["body"]
        assert isinstance(body, bytes)
        return {"Body": io.BytesIO(body)}


def _store(client: FakeS3Client) -> S3ObjectStore:
    store = object.__new__(S3ObjectStore)
    store.client = client  # type: ignore[assignment]
    return store


def test_oss_client_uses_signature_v2_and_virtual_host_addressing() -> None:
    with patch("lumi_asset_storage.s3.boto3.client") as client:
        S3ObjectStore(
            endpoint_url="https://s3.oss-cn-hangzhou-internal.aliyuncs.com",
            region_name="cn-hangzhou",
            access_key_id="test-access-key",
            secret_access_key="test-secret-key",
            session_token="test-session-token",
            signature_version="s3",
            force_path_style=False,
        )
    kwargs = client.call_args.kwargs
    assert kwargs["aws_session_token"] == "test-session-token"
    assert kwargs["config"].signature_version == "s3"
    assert kwargs["config"].s3["addressing_style"] == "virtual"


def test_s3_client_rejects_unknown_signature_version() -> None:
    with pytest.raises(ValueError, match="S3_SIGNATURE_VERSION_INVALID"):
        S3ObjectStore(
            endpoint_url=None,
            region_name="us-east-1",
            access_key_id=None,
            secret_access_key=None,
            signature_version="unsigned-v1",
        )


def test_put_bytes_persists_sha256_and_metadata_without_unbounded_upload() -> None:
    client = FakeS3Client()
    store = _store(client)
    payload = b"provider-image-bytes"
    head = asyncio.run(
        store.put_bytes(
            bucket="assets",
            object_key="provider-output/v1/a.png",
            data=payload,
            content_type="image/png",
            max_bytes=1024,
            metadata={"provider": "openai"},
        )
    )
    expected = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii")
    assert head.content_length == len(payload)
    assert head.checksum_sha256_b64 == expected
    assert client.last_put is not None
    assert client.last_put["ChecksumSHA256"] == expected
    assert client.last_put["Body"] == payload
    assert client.last_put["Metadata"] == {"provider": "openai"}


def test_put_bytes_rejects_oversized_payload_before_s3_call() -> None:
    client = FakeS3Client()
    store = _store(client)
    with pytest.raises(ValueError, match="S3_OBJECT_TOO_LARGE"):
        asyncio.run(
            store.put_bytes(
                bucket="assets",
                object_key="provider-output/v1/a.png",
                data=b"12345",
                content_type="image/png",
                max_bytes=4,
            )
        )
    assert client.last_put is None


def test_get_bytes_uses_head_limit_and_returns_exact_payload() -> None:
    client = FakeS3Client()
    payload = b"stored-image"
    client.put_object(
        Bucket="assets",
        Key="provider-output/v1/a.png",
        Body=payload,
        ContentType="image/png",
        ChecksumSHA256="checksum",
        Metadata={},
    )
    store = _store(client)
    assert (
        asyncio.run(
            store.get_bytes(
                bucket="assets",
                object_key="provider-output/v1/a.png",
                max_bytes=len(payload),
            )
        )
        == payload
    )


def test_get_bytes_rejects_object_larger_than_bound_before_download() -> None:
    client = FakeS3Client()
    client.put_object(
        Bucket="assets",
        Key="provider-output/v1/a.png",
        Body=b"12345",
        ContentType="image/png",
        ChecksumSHA256="checksum",
        Metadata={},
    )
    store = _store(client)
    with pytest.raises(ValueError, match="S3_OBJECT_TOO_LARGE"):
        asyncio.run(
            store.get_bytes(
                bucket="assets",
                object_key="provider-output/v1/a.png",
                max_bytes=4,
            )
        )
