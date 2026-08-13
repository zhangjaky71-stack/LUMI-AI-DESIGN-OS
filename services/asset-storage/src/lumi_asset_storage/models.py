from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

UploadStatus = Literal["pending", "completed", "expired", "aborted", "rejected"]
AssetStatus = Literal["uploading", "scanning", "ready", "rejected"]
RightsAssertion = Literal["USER_OWNED", "LICENSED", "UNKNOWN"]
ScanStatus = Literal["CLEAN", "INFECTED", "SCAN_UNAVAILABLE", "ERROR"]


@dataclass(frozen=True, slots=True)
class UploadRequest:
    bucket: str
    object_key: str
    content_type: str
    checksum_sha256_b64: str
    expires_seconds: int
    content_length: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SignedUpload:
    url: str
    method: Literal["PUT"]
    required_headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class MultipartUpload:
    upload_id: str
    bucket: str
    object_key: str


@dataclass(frozen=True, slots=True)
class SignedPartUpload:
    part_number: int
    url: str
    method: Literal["PUT"]
    required_headers: dict[str, str]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CompletedPart:
    part_number: int
    etag: str
    checksum_sha256_b64: str | None = None


@dataclass(frozen=True, slots=True)
class ObjectHead:
    bucket: str
    object_key: str
    content_length: int
    content_type: str | None
    checksum_sha256_b64: str | None
    etag: str | None
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class SignedDownload:
    url: str
    expires_at: datetime


class ObjectStore(Protocol):
    async def create_upload(self, request: UploadRequest) -> SignedUpload: ...

    async def create_multipart_upload(self, request: UploadRequest) -> MultipartUpload: ...

    async def create_part_upload(
        self,
        upload: MultipartUpload,
        *,
        part_number: int,
        checksum_sha256_b64: str | None,
        expires_seconds: int,
    ) -> SignedPartUpload: ...

    async def complete_multipart_upload(
        self,
        upload: MultipartUpload,
        *,
        parts: tuple[CompletedPart, ...],
        checksum_sha256_b64: str | None,
    ) -> None: ...

    async def abort_multipart_upload(self, upload: MultipartUpload) -> None: ...

    async def head(self, *, bucket: str, object_key: str) -> ObjectHead: ...

    async def get_signed_download(
        self,
        *,
        bucket: str,
        object_key: str,
        expires_seconds: int,
        download_name: str | None,
        attachment: bool,
    ) -> SignedDownload: ...

    async def copy(
        self,
        *,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> None: ...

    async def download_to_path(self, *, bucket: str, object_key: str, path: str) -> None: ...

    async def upload_from_path(
        self,
        *,
        bucket: str,
        object_key: str,
        path: str,
        content_type: str,
        checksum_sha256_b64: str,
    ) -> ObjectHead: ...

    async def delete_candidate(self, *, bucket: str, object_key: str) -> None: ...


class FileScanner(Protocol):
    async def scan_path(self, path: str) -> ScanStatus: ...
