from __future__ import annotations

import hashlib
import os
import urllib.request
from datetime import UTC, datetime

from lumi_api.assets import S3CompatibleObjectStore, UploadIntent

ENDPOINT = os.environ.get("LUMI_MINIO_ENDPOINT", "http://127.0.0.1:9000")
ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "lumi-local")
SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "lumi_minio_local_only")
BUCKET = os.environ.get("MINIO_BUCKET_ASSETS", "lumi-assets")


def main() -> None:
    now = datetime.now(UTC)
    payload = b"\x89PNG\r\n\x1a\n" + b"NODE18-MINIO-ROUNDTRIP" * 128
    checksum = hashlib.sha256(payload).hexdigest()
    key = "org/node18/project/fixture/asset/roundtrip/original/file"
    store = S3CompatibleObjectStore(
        endpoint=ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
    )
    intent = UploadIntent(
        bucket=BUCKET,
        key=key,
        expected_checksum_sha256=checksum,
        declared_mime_type="image/png",
        expires_seconds=300,
    )
    signed = store.create_upload(intent, now=now)
    request = urllib.request.Request(signed.url, data=payload, method="PUT")
    request.add_header("Content-Type", "image/png")
    for name, value in signed.headers.items():
        request.add_header(name, value)
    urllib.request.urlopen(request, timeout=60).read()

    head = store.head(BUCKET, key, now=now)
    assert head.exists
    assert head.byte_size == len(payload)
    if head.checksum_sha256 is not None:
        assert head.checksum_sha256 == checksum
    assert b"".join(store.iter_bytes(BUCKET, key, now=now)) == payload

    download = store.get_signed_download(
        BUCKET,
        key,
        filename="roundtrip.png",
        expires_seconds=120,
        now=now,
    )
    assert urllib.request.urlopen(download.url, timeout=60).read() == payload

    copy_key = key + "-copy"
    store.copy(BUCKET, key, copy_key, now=now)
    assert store.head(BUCKET, copy_key, now=now).byte_size == len(payload)
    store.delete_candidate(BUCKET, copy_key, now=now)
    store.delete_candidate(BUCKET, key, now=now)
    print("NODE18_MINIO_ROUNDTRIP_PASS")


if __name__ == "__main__":
    main()
