from __future__ import annotations

import base64
import hashlib
import hmac
import io
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from .models import ObjectHead, SignedRequest


@dataclass(frozen=True, slots=True)
class UploadIntent:
    bucket: str
    key: str
    expected_checksum_sha256: str
    declared_mime_type: str
    expires_seconds: int


class ObjectStore(Protocol):
    def create_upload(self, intent: UploadIntent, *, now: datetime) -> SignedRequest: ...

    def start_multipart(self, intent: UploadIntent, *, now: datetime) -> str: ...

    def sign_part(
        self,
        intent: UploadIntent,
        *,
        upload_id: str,
        part_number: int,
        now: datetime,
    ) -> SignedRequest: ...

    def complete_multipart(
        self,
        intent: UploadIntent,
        *,
        upload_id: str,
        parts: tuple[tuple[int, str], ...],
        now: datetime,
    ) -> None: ...

    def abort_multipart(
        self, intent: UploadIntent, *, upload_id: str, now: datetime
    ) -> None: ...

    def head(self, bucket: str, key: str, *, now: datetime) -> ObjectHead: ...

    def iter_bytes(self, bucket: str, key: str, *, now: datetime) -> Iterator[bytes]: ...

    def put_derived(
        self,
        bucket: str,
        key: str,
        content: bytes,
        *,
        content_type: str,
        checksum_sha256: str,
        now: datetime,
    ) -> None: ...

    def get_signed_download(
        self,
        bucket: str,
        key: str,
        *,
        filename: str,
        expires_seconds: int,
        now: datetime,
    ) -> SignedRequest: ...

    def copy(self, bucket: str, source_key: str, target_key: str, *, now: datetime) -> None: ...

    def delete_candidate(self, bucket: str, key: str, *, now: datetime) -> None: ...


@dataclass(slots=True)
class MemoryObjectStore(ObjectStore):
    objects: dict[tuple[str, str], bytes] = field(default_factory=dict)
    content_types: dict[tuple[str, str], str] = field(default_factory=dict)
    multipart: dict[str, dict[int, bytes]] = field(default_factory=dict)
    _counter: int = 0

    def create_upload(self, intent: UploadIntent, *, now: datetime) -> SignedRequest:
        return SignedRequest(
            method="PUT",
            url=f"memory://{intent.bucket}/{intent.key}",
            expires_at=now + timedelta(seconds=intent.expires_seconds),
            headers={"x-lumi-checksum-sha256": intent.expected_checksum_sha256},
        )

    def set_uploaded_bytes(self, intent: UploadIntent, content: bytes) -> None:
        self.objects[(intent.bucket, intent.key)] = content
        self.content_types[(intent.bucket, intent.key)] = intent.declared_mime_type

    def start_multipart(self, intent: UploadIntent, *, now: datetime) -> str:
        _ = (intent, now)
        self._counter += 1
        upload_id = f"memory-upload-{self._counter}"
        self.multipart[upload_id] = {}
        return upload_id

    def sign_part(
        self,
        intent: UploadIntent,
        *,
        upload_id: str,
        part_number: int,
        now: datetime,
    ) -> SignedRequest:
        if upload_id not in self.multipart:
            raise ValueError("MULTIPART_UPLOAD_NOT_FOUND")
        return SignedRequest(
            method="PUT",
            url=f"memory://{intent.bucket}/{intent.key}?uploadId={upload_id}&partNumber={part_number}",
            expires_at=now + timedelta(seconds=intent.expires_seconds),
        )

    def set_part(self, upload_id: str, part_number: int, content: bytes) -> None:
        self.multipart[upload_id][part_number] = content

    def complete_multipart(
        self,
        intent: UploadIntent,
        *,
        upload_id: str,
        parts: tuple[tuple[int, str], ...],
        now: datetime,
    ) -> None:
        _ = (parts, now)
        uploaded = self.multipart.pop(upload_id, None)
        if uploaded is None:
            raise ValueError("MULTIPART_UPLOAD_NOT_FOUND")
        content = b"".join(uploaded[number] for number in sorted(uploaded))
        self.set_uploaded_bytes(intent, content)

    def abort_multipart(
        self, intent: UploadIntent, *, upload_id: str, now: datetime
    ) -> None:
        _ = (intent, now)
        self.multipart.pop(upload_id, None)

    def head(self, bucket: str, key: str, *, now: datetime) -> ObjectHead:
        _ = now
        content = self.objects.get((bucket, key))
        if content is None:
            return ObjectHead(bucket=bucket, key=key, exists=False, byte_size=0)
        return ObjectHead(
            bucket=bucket,
            key=key,
            byte_size=len(content),
            content_type=self.content_types.get((bucket, key)),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            etag=hashlib.md5(content, usedforsecurity=False).hexdigest(),
        )

    def iter_bytes(self, bucket: str, key: str, *, now: datetime) -> Iterator[bytes]:
        _ = now
        content = self.objects.get((bucket, key))
        if content is None:
            raise FileNotFoundError(key)
        for offset in range(0, len(content), 1024 * 1024):
            yield content[offset : offset + 1024 * 1024]

    def put_derived(
        self,
        bucket: str,
        key: str,
        content: bytes,
        *,
        content_type: str,
        checksum_sha256: str,
        now: datetime,
    ) -> None:
        _ = now
        if hashlib.sha256(content).hexdigest() != checksum_sha256:
            raise ValueError("DERIVED_CHECKSUM_MISMATCH")
        self.objects[(bucket, key)] = content
        self.content_types[(bucket, key)] = content_type

    def get_signed_download(
        self,
        bucket: str,
        key: str,
        *,
        filename: str,
        expires_seconds: int,
        now: datetime,
    ) -> SignedRequest:
        if (bucket, key) not in self.objects:
            raise FileNotFoundError(key)
        return SignedRequest(
            method="GET",
            url=f"memory://{bucket}/{key}?filename={urllib.parse.quote(filename)}",
            expires_at=now + timedelta(seconds=expires_seconds),
        )

    def copy(self, bucket: str, source_key: str, target_key: str, *, now: datetime) -> None:
        _ = now
        content = self.objects[(bucket, source_key)]
        self.objects[(bucket, target_key)] = content
        self.content_types[(bucket, target_key)] = self.content_types.get((bucket, source_key), "")

    def delete_candidate(self, bucket: str, key: str, *, now: datetime) -> None:
        _ = now
        self.objects.pop((bucket, key), None)
        self.content_types.pop((bucket, key), None)


class S3CompatibleObjectStore(ObjectStore):
    """Dependency-free SigV4/path-style adapter for MinIO and S3-compatible stores."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region

    def _presign(
        self,
        method: str,
        bucket: str,
        key: str,
        *,
        now: datetime,
        expires_seconds: int,
        query: dict[str, str] | None = None,
        signed_headers: dict[str, str] | None = None,
    ) -> SignedRequest:
        if not 1 <= expires_seconds <= 900:
            raise ValueError("SIGNED_URL_TTL_OUT_OF_RANGE")
        parsed = urllib.parse.urlsplit(self.endpoint)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("OBJECT_STORE_ENDPOINT_INVALID")
        timestamp = now.astimezone(UTC)
        amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
        date = timestamp.strftime("%Y%m%d")
        scope = f"{date}/{self.region}/s3/aws4_request"
        canonical_uri = "/" + "/".join(
            urllib.parse.quote(part, safe="-_.~") for part in (bucket, *key.split("/"))
        )
        headers = {"host": parsed.netloc}
        for name, value in (signed_headers or {}).items():
            headers[name.casefold().strip()] = value.strip()
        signed_names = ";".join(sorted(headers))
        params = dict(query or {})
        params.update(
            {
                "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
                "X-Amz-Credential": f"{self.access_key}/{scope}",
                "X-Amz-Date": amz_date,
                "X-Amz-Expires": str(expires_seconds),
                "X-Amz-SignedHeaders": signed_names,
            }
        )
        canonical_query = urllib.parse.urlencode(sorted(params.items()), quote_via=urllib.parse.quote)
        canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
        canonical_request = "\n".join(
            [method, canonical_uri, canonical_query, canonical_headers, signed_names, "UNSIGNED-PAYLOAD"]
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        key_date = hmac.new(("AWS4" + self.secret_key).encode(), date.encode(), hashlib.sha256).digest()
        key_region = hmac.new(key_date, self.region.encode(), hashlib.sha256).digest()
        key_service = hmac.new(key_region, b"s3", hashlib.sha256).digest()
        signing_key = hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()
        signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        url = f"{parsed.scheme}://{parsed.netloc}{canonical_uri}?{canonical_query}&X-Amz-Signature={signature}"
        client_headers = {name: value for name, value in headers.items() if name != "host"}
        return SignedRequest(
            method=method,  # type: ignore[arg-type]
            url=url,
            expires_at=timestamp + timedelta(seconds=expires_seconds),
            headers=client_headers,
        )

    @staticmethod
    def _checksum_header(hex_digest: str) -> str:
        return base64.b64encode(bytes.fromhex(hex_digest)).decode()

    def create_upload(self, intent: UploadIntent, *, now: datetime) -> SignedRequest:
        return self._presign(
            "PUT",
            intent.bucket,
            intent.key,
            now=now,
            expires_seconds=intent.expires_seconds,
            signed_headers={"x-amz-checksum-sha256": self._checksum_header(intent.expected_checksum_sha256)},
        )

    def start_multipart(self, intent: UploadIntent, *, now: datetime) -> str:
        request = self._presign(
            "POST", intent.bucket, intent.key, now=now, expires_seconds=60, query={"uploads": ""}
        )
        response = urllib.request.urlopen(urllib.request.Request(request.url, method="POST"), timeout=30)
        root = ET.fromstring(response.read())
        upload_id = next((node.text for node in root.iter() if node.tag.endswith("UploadId")), None)
        if not upload_id:
            raise RuntimeError("S3_MULTIPART_UPLOAD_ID_MISSING")
        return upload_id

    def sign_part(
        self,
        intent: UploadIntent,
        *,
        upload_id: str,
        part_number: int,
        now: datetime,
    ) -> SignedRequest:
        if not 1 <= part_number <= 10_000:
            raise ValueError("MULTIPART_PART_NUMBER_INVALID")
        return self._presign(
            "PUT",
            intent.bucket,
            intent.key,
            now=now,
            expires_seconds=intent.expires_seconds,
            query={"partNumber": str(part_number), "uploadId": upload_id},
        )

    def complete_multipart(
        self,
        intent: UploadIntent,
        *,
        upload_id: str,
        parts: tuple[tuple[int, str], ...],
        now: datetime,
    ) -> None:
        if not parts:
            raise ValueError("MULTIPART_PARTS_REQUIRED")
        root = ET.Element("CompleteMultipartUpload")
        for number, etag in sorted(parts):
            part = ET.SubElement(root, "Part")
            ET.SubElement(part, "PartNumber").text = str(number)
            ET.SubElement(part, "ETag").text = etag
        body = ET.tostring(root, encoding="utf-8")
        signed = self._presign(
            "POST",
            intent.bucket,
            intent.key,
            now=now,
            expires_seconds=60,
            query={"uploadId": upload_id},
        )
        request = urllib.request.Request(signed.url, data=body, method="POST")
        request.add_header("Content-Type", "application/xml")
        urllib.request.urlopen(request, timeout=60).read()

    def abort_multipart(
        self, intent: UploadIntent, *, upload_id: str, now: datetime
    ) -> None:
        signed = self._presign(
            "DELETE",
            intent.bucket,
            intent.key,
            now=now,
            expires_seconds=60,
            query={"uploadId": upload_id},
        )
        urllib.request.urlopen(urllib.request.Request(signed.url, method="DELETE"), timeout=30).read()

    def head(self, bucket: str, key: str, *, now: datetime) -> ObjectHead:
        signed = self._presign("HEAD", bucket, key, now=now, expires_seconds=60)
        try:
            response = urllib.request.urlopen(
                urllib.request.Request(signed.url, method="HEAD"), timeout=30
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return ObjectHead(bucket=bucket, key=key, exists=False, byte_size=0)
            raise
        checksum_b64 = response.headers.get("x-amz-checksum-sha256")
        checksum = None
        if checksum_b64:
            checksum = base64.b64decode(checksum_b64).hex()
        return ObjectHead(
            bucket=bucket,
            key=key,
            byte_size=int(response.headers.get("Content-Length", "0")),
            content_type=response.headers.get("Content-Type"),
            checksum_sha256=checksum,
            etag=response.headers.get("ETag", "").strip('"') or None,
        )

    def iter_bytes(self, bucket: str, key: str, *, now: datetime) -> Iterator[bytes]:
        signed = self._presign("GET", bucket, key, now=now, expires_seconds=120)
        with urllib.request.urlopen(signed.url, timeout=180) as response:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    def put_derived(
        self,
        bucket: str,
        key: str,
        content: bytes,
        *,
        content_type: str,
        checksum_sha256: str,
        now: datetime,
    ) -> None:
        signed = self._presign(
            "PUT",
            bucket,
            key,
            now=now,
            expires_seconds=60,
            signed_headers={"x-amz-checksum-sha256": self._checksum_header(checksum_sha256)},
        )
        request = urllib.request.Request(signed.url, data=content, method="PUT")
        request.add_header("Content-Type", content_type)
        for name, value in signed.headers.items():
            request.add_header(name, value)
        urllib.request.urlopen(request, timeout=120).read()

    def get_signed_download(
        self,
        bucket: str,
        key: str,
        *,
        filename: str,
        expires_seconds: int,
        now: datetime,
    ) -> SignedRequest:
        disposition = f'attachment; filename="{filename.replace(chr(34), "_")}"'
        return self._presign(
            "GET",
            bucket,
            key,
            now=now,
            expires_seconds=expires_seconds,
            query={"response-content-disposition": disposition},
        )

    def copy(self, bucket: str, source_key: str, target_key: str, *, now: datetime) -> None:
        source = "/" + "/".join(urllib.parse.quote(part, safe="-_.~") for part in (bucket, *source_key.split("/")))
        signed = self._presign(
            "PUT",
            bucket,
            target_key,
            now=now,
            expires_seconds=60,
            signed_headers={"x-amz-copy-source": source},
        )
        request = urllib.request.Request(signed.url, method="PUT")
        for name, value in signed.headers.items():
            request.add_header(name, value)
        urllib.request.urlopen(request, timeout=60).read()

    def delete_candidate(self, bucket: str, key: str, *, now: datetime) -> None:
        signed = self._presign("DELETE", bucket, key, now=now, expires_seconds=60)
        urllib.request.urlopen(urllib.request.Request(signed.url, method="DELETE"), timeout=30).read()
