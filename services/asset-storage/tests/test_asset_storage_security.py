from __future__ import annotations

import pytest

from lumi_asset_storage.sniff import (
    require_declared_mime_matches_sniffed,
    sniff_media_type,
)
from lumi_asset_storage.svg import sanitize_svg


def test_magic_bytes_override_untrusted_declared_mime() -> None:
    sniffed = sniff_media_type(b"\x89PNG\r\n\x1a\n" + b"x" * 32)
    assert sniffed.mime_type == "image/png"
    with pytest.raises(ValueError, match="DECLARED_MIME_MISMATCH"):
        require_declared_mime_matches_sniffed("image/svg+xml", sniffed.mime_type)


def test_arbitrary_html_is_not_accepted_as_media() -> None:
    with pytest.raises(ValueError, match="UNSUPPORTED_OR_UNRECOGNIZED_MEDIA"):
        sniff_media_type(b"<html><script>alert(1)</script></html>")


def test_svg_xml_declaration_is_sniffed_but_active_content_is_rejected() -> None:
    payload = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert sniff_media_type(payload).mime_type == "image/svg+xml"
    with pytest.raises(ValueError, match="SVG_ACTIVE_CONTENT_REJECTED"):
        sanitize_svg(payload)


@pytest.mark.parametrize(
    "payload,error",
    [
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil.example/x.png"/></svg>',
            "SVG_DANGEROUS_REFERENCE|SVG_EXTERNAL_REFERENCE_REJECTED",
        ),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><rect onload="alert(1)"/></svg>',
            "SVG_EVENT_HANDLER_REJECTED",
        ),
        (
            b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
            "SVG_DTD_OR_ENTITY_REJECTED",
        ),
        (
            b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import url(https://evil.example/x.css)</style></svg>',
            "SVG_DANGEROUS_REFERENCE|SVG_DANGEROUS_STYLE",
        ),
    ],
)
def test_svg_rejects_active_or_external_content(payload: bytes, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        sanitize_svg(payload)


def test_svg_allows_internal_fragment_reference() -> None:
    payload = b'<svg xmlns="http://www.w3.org/2000/svg"><defs><path id="p" d="M0 0"/></defs><use href="#p"/></svg>'
    cleaned = sanitize_svg(payload)
    assert b"script" not in cleaned.lower()
    assert b"#p" in cleaned


def test_svg_size_limit_fails_closed() -> None:
    payload = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    with pytest.raises(ValueError, match="SVG_TOO_LARGE"):
        sanitize_svg(payload, max_bytes=8)
