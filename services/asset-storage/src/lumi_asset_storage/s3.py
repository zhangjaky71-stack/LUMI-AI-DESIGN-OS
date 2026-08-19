from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from .models import (
    CompletedPart,
    MultipartUpload,
    ObjectHead,
    SignedDownload,
    SignedPartUpload,
    SignedUpload,
    UploadRequest,
)


class S3ObjectStore:
    def __init__(
        self,
        *,
        endpoint_url: str | None,
        region_name: str,
        access_key_id: str | None,
        secret_access_key: str | None,
        force_path_style: bool = False,
    ) -> None:
        config = Config(
            signature_version="s3v4",
            retries={"mode": "standard", "max_attempts": 4},
            s3={"addressing_style": "path" if force_path_style else "auto"},
        )
        self.client: BaseClient = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=config,
        )

    async def create_upload(self, request: UploadRequest) -> SignedUpload:
        params: dict[str, Any] = {
            "Bucket": request.bucket,
            "Key": request.object_key,
            "ContentType": request.content_type,
            "ChecksumSHA256": request.checksum_sha256_b64,
            "Metadata": request.metadata,
        }
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object",
            Params=params,
            ExpiresIn=request.expires_seconds,
            HttpMethod="PUT",
        )
        return SignedUpload(
            url=url,
            method="PUT",
            required_headers={
                "Content-Type": request.content_type,
                "x-amz-checksum-sha256": request.checksum_sha256_b64,
            },
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_seconds),
        )

    async def create_multipart_upload(self, request: UploadRequest) -> MultipartUpload:
        response = await asyncio.to_thread(
            self.client.create_multipart_upload,
            Bucket=request.bucket,
            Key=request.object_key,
            ContentType=request.content_type,
            ChecksumAlgorithm="SHA256",
            Metadata=request.metadata,
        )
        return MultipartUpload(
            upload_id=str(response["UploadId"]),
            bucket=request.bucket,
            object_key=request.object_key,
        )

    async def create_part_upload(
        self,
        upload: MultipartUpload,
        *,
        part_number: int,
        checksum_sha256_b64: str | None,
        expires_seconds: int,
    ) -> SignedPartUpload:
        if not 1 <= part_number <= 10_000:
            raise ValueError("MULTIPART_PART_NUMBER_INVALID")
        params: dict[str, Any] = {
            "Bucket": upload.bucket,
            "Key": upload.object_key,
            "UploadId": upload.upload_id,
            "PartNumber": part_number,
        }
        required_headers: dict[str, str] = {}
        if checksum_sha256_b64 is not None:
            params["ChecksumSHA256"] = checksum_sha256_b64
            required_headers["x-amz-checksum-sha256"] = checksum_sha256_b64
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "upload_part",
            Params=params,
            ExpiresIn=expires_seconds,
            HttpMethod="PUT",
        )
        return SignedPartUpload(
            part_number=part_number,
            url=url,
            method="PUT",
            required_headers=required_headers,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_seconds),
        )

    async def complete_multipart_upload(
        self,
        upload: MultipartUpload,
        *,
        parts: tuple[CompletedPart, ...],
        checksum_sha256_b64: str | None,
    ) -> None:
        if not parts:
            raise ValueError("MULTIPART_PARTS_REQUIRED")
        numbers = [part.part_number for part in parts]
        if numbers != list(range(1, len(parts) + 1)):
            raise ValueError("MULTIPART_PARTS_MUST_BE_CONSECUTIVE")
        serialized: list[dict[str, Any]] = []
        for part in parts:
            row: dict[str, Any] = {"PartNumber": part.part_number, "ETag": part.etag}
            if part.checksum_sha256_b64 is not None:
                row["ChecksumSHA256"] = part.checksum_sha256_b64
            serialized.append(row)
        kwargs: dict[str, Any] = {
            "Bucket": upload.bucket,
            "Key": upload.object_key,
            "UploadId": upload.upload_id,
            "MultipartUpload": {"Parts": serialized},
        }
        if checksum_sha256_b64 is not None:
            kwargs["ChecksumSHA256"] = checksum_sha256_b64
        await asyncio.to_thread(self.client.complete_multipart_upload, **kwargs)

    async def abort_multipart_upload(self, upload: MultipartUpload) -> None:
        await asyncio.to_thread(
            self.client.abort_multipart_upload,
            Bucket=upload.bucket,
            Key=upload.object_key,
            UploadId=upload.upload_id,
        )

    async def head(self, *, bucket: str, object_key: str) -> ObjectHead:
        response = await asyncio.to_thread(
            self.client.head_object,
            Bucket=bucket,
            Key=object_key,
            ChecksumMode="ENABLED",
        )
        metadata = {
            str(key).lower(): str(value)
            for key, value in dict(response.get("Metadata", {})).items()
        }
        return ObjectHead(
            bucket=bucket,
            object_key=object_key,
            content_length=int(response["ContentLength"]),
            content_type=response.get("ContentType"),
            checksum_sha256_b64=response.get("ChecksumSHA256"),
            etag=str(response.get("ETag", "")).strip('"') or None,
            metadata=metadata,
        )

    async def get_signed_download(
        self,
        *,
        bucket: str,
        object_key: str,
        expires_seconds: int,
        download_name: str | None,
        attachment: bool,
    ) -> SignedDownload:
        params: dict[str, Any] = {"Bucket": bucket, "Key": object_key}
        if download_name:
            disposition = "attachment" if attachment else "inline"
            safe_name = quote(download_name, safe="")
            params["ResponseContentDisposition"] = (
                f"{disposition}; filename*=UTF-8''{safe_name}"
            )
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params=params,
            ExpiresIn=expires_seconds,
            HttpMethod="GET",
        )
        return SignedDownload(
            url=url,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_seconds),
        )

    async def copy(
        self,
        *,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> None:
        await asyncio.to_thread(
            self.client.copy_object,
            Bucket=destination_bucket,
            Key=destination_key,
            CopySource={"Bucket": source_bucket, "Key": source_key},
            MetadataDirective="COPY",
        )

    async def download_to_path(self, *, bucket: str, object_key: str, path: str) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            self.client.download_file,
            bucket,
            object_key,
            str(destination),
        )

    async def upload_from_path(
        self,
        *,
        bucket: str,
        object_key: str,
        path: str,
        content_type: str,
        checksum_sha256_b64: str,
    ) -> ObjectHead:
        with Path(path).open("rb") as handle:
            await asyncio.to_thread(
                self.client.put_object,
                Bucket=bucket,
                Key=object_key,
                Body=handle,
                ContentType=content_type,
                ChecksumSHA256=checksum_sha256_b64,
            )
        return await self.head(bucket=bucket, object_key=object_key)

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
        if not bucket or not object_key:
            raise ValueError("S3_OBJECT_LOCATION_REQUIRED")
        if not content_type or "\x00" in content_type:
            raise ValueError("S3_CONTENT_TYPE_INVALID")
        if max_bytes <= 0:
            raise ValueError("S3_MAX_BYTES_INVALID")
        if not isinstance(data, bytes):
            raise TypeError("S3_BYTES_REQUIRED")
        if len(data) > max_bytes:
            raise ValueError("S3_OBJECT_TOO_LARGE")
        checksum = base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
            ChecksumSHA256=checksum,
            Metadata=dict(metadata or {}),
        )
        return await self.head(bucket=bucket, object_key=object_key)

    async def get_bytes(
        self,
        *,
        bucket: str,
        object_key: str,
        max_bytes: int,
    ) -> bytes:
        if not bucket or not object_key:
            raise ValueError("S3_OBJECT_LOCATION_REQUIRED")
        if max_bytes <= 0:
            raise ValueError("S3_MAX_BYTES_INVALID")
        head = await self.head(bucket=bucket, object_key=object_key)
        if head.content_length > max_bytes:
            raise ValueError("S3_OBJECT_TOO_LARGE")
        response = await asyncio.to_thread(
            self.client.get_object,
            Bucket=bucket,
            Key=object_key,
        )
        body = response.get("Body")
        if body is None or not hasattr(body, "read"):
            raise RuntimeError("S3_OBJECT_BODY_MISSING")
        try:
            data = await asyncio.to_thread(body.read, max_bytes + 1)
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                await asyncio.to_thread(close)
        if not isinstance(data, bytes):
            raise RuntimeError("S3_OBJECT_BODY_INVALID")
        if len(data) > max_bytes:
            raise ValueError("S3_OBJECT_TOO_LARGE")
        return data

    async def delete_candidate(self, *, bucket: str, object_key: str) -> None:
        await asyncio.to_thread(
            self.client.delete_object,
            Bucket=bucket,
            Key=object_key,
        )
