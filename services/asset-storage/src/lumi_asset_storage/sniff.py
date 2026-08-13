from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SniffResult:
    mime_type: str
    family: str


_SUPPORTED = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/svg+xml",
        "application/pdf",
        "video/mp4",
        "video/quicktime",
        "video/webm",
        "font/ttf",
        "font/otf",
        "font/woff2",
    }
)


def supported_mime_types() -> frozenset[str]:
    return _SUPPORTED


def sniff_media_type(prefix: bytes) -> SniffResult:
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return SniffResult("image/png", "image")
    if prefix.startswith(b"\xff\xd8\xff"):
        return SniffResult("image/jpeg", "image")
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return SniffResult("image/webp", "image")
    if prefix.startswith(b"%PDF-"):
        return SniffResult("application/pdf", "document")
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
        major_brand = prefix[8:12]
        if major_brand == b"qt  ":
            return SniffResult("video/quicktime", "video")
        return SniffResult("video/mp4", "video")
    if prefix.startswith(b"\x1aE\xdf\xa3"):
        return SniffResult("video/webm", "video")
    if prefix.startswith(b"\x00\x01\x00\x00") or prefix.startswith(b"true"):
        return SniffResult("font/ttf", "font")
    if prefix.startswith(b"OTTO"):
        return SniffResult("font/otf", "font")
    if prefix.startswith(b"wOF2"):
        return SniffResult("font/woff2", "font")

    text = prefix[:16384].decode("utf-8-sig", errors="ignore").lstrip()
    text_without_xml = re.sub(r"^<\?xml[^>]*>\s*", "", text, count=1, flags=re.IGNORECASE)
    if re.match(r"^<svg(?:\s|>)", text_without_xml, flags=re.IGNORECASE):
        return SniffResult("image/svg+xml", "vector")
    raise ValueError("UNSUPPORTED_OR_UNRECOGNIZED_MEDIA")


def require_declared_mime_matches_sniffed(declared: str, sniffed: str) -> None:
    normalized = declared.split(";", 1)[0].strip().lower()
    aliases = {
        "image/jpg": "image/jpeg",
        "application/x-font-ttf": "font/ttf",
        "application/x-font-otf": "font/otf",
        "application/font-woff2": "font/woff2",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized != sniffed:
        raise ValueError("DECLARED_MIME_MISMATCH")
