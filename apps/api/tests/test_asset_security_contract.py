from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from lumi_api.assets import S3CompatibleObjectStore, UploadIntent, sanitize_filename, sanitize_svg, sniff_mime

NOW = datetime(2026, 8, 16, 8, 20, tzinfo=UTC)


def test_sniffer_uses_magic_bytes_not_extension_or_declared_type() -> None:
    payload = b"\x89PNG\r\n\x1a\n" + b"x" * 64
    mime, kind = sniff_mime(payload)
    assert mime == "image/png"
    assert kind.value == "image"


def test_svg_sanitizer_rejects_script_events_and_external_resources() -> None:
    fixtures = (
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><g onclick="x()"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil.invalid/a"/></svg>',
        b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg>&x;</svg>',
    )
    for payload in fixtures:
        with pytest.raises(ValueError):
            sanitize_svg(payload)


def test_svg_sanitizer_accepts_fragment_only_references() -> None:
    safe = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<defs><path id="a" d="M0 0"/></defs><use href="#a"/></svg>'
    )
    sanitized = sanitize_svg(safe)
    assert b"script" not in sanitized.lower()
    assert b"http://evil" not in sanitized.lower()


def test_filename_sanitization_removes_paths_and_control_characters() -> None:
    assert sanitize_filename("../../unsafe\x00 name?.png") == "unsafe name_.png"


def test_s3_sigv4_presign_never_exposes_secret_and_binds_checksum_header() -> None:
    secret = "super-secret-test-value"
    store = S3CompatibleObjectStore(
        endpoint="http://127.0.0.1:9000",
        access_key="AKIDEXAMPLE",
        secret_key=secret,
    )
    checksum = hashlib.sha256(b"hello").hexdigest()
    intent = UploadIntent(
        bucket="lumi-assets",
        key="org/o/project/p/asset/a/original/f",
        expected_checksum_sha256=checksum,
        declared_mime_type="image/png",
        expires_seconds=300,
    )
    signed = store.create_upload(intent, now=NOW)
    assert "X-Amz-Signature=" in signed.url
    assert secret not in signed.url
    assert signed.expires_at == NOW + timedelta(seconds=300)
    assert signed.headers["x-amz-checksum-sha256"] == base64.b64encode(
        bytes.fromhex(checksum)
    ).decode()


def test_signed_url_ttl_is_hard_capped() -> None:
    store = S3CompatibleObjectStore(
        endpoint="http://127.0.0.1:9000",
        access_key="key",
        secret_key="secret",
    )
    with pytest.raises(ValueError, match="SIGNED_URL_TTL_OUT_OF_RANGE"):
        store.get_signed_download(
            "lumi-assets",
            "a/b",
            filename="x.png",
            expires_seconds=901,
            now=NOW,
        )
