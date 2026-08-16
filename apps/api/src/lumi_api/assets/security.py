from __future__ import annotations

import json
import re
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Protocol

from .models import FileScanResult, MediaKind, ScanStatus

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._()\- ]+")
_SVG_FORBIDDEN_TEXT = re.compile(
    r"<!DOCTYPE|<!ENTITY|javascript:|data:text/html|<\s*script\b|<\s*foreignObject\b",
    re.IGNORECASE,
)

SUPPORTED_MIME_KIND: dict[str, MediaKind] = {
    "image/png": MediaKind.IMAGE,
    "image/jpeg": MediaKind.IMAGE,
    "image/webp": MediaKind.IMAGE,
    "image/svg+xml": MediaKind.VECTOR,
    "application/pdf": MediaKind.DOCUMENT,
    "video/mp4": MediaKind.VIDEO,
    "video/quicktime": MediaKind.VIDEO,
    "video/webm": MediaKind.VIDEO,
    "font/ttf": MediaKind.FONT,
    "font/otf": MediaKind.FONT,
    "font/woff2": MediaKind.FONT,
}


def sanitize_filename(filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1].strip().replace("\x00", "")
    name = _SAFE_FILENAME.sub("_", name).strip(" .")
    if not name:
        name = "download"
    return name[:255]


def sniff_mime(prefix: bytes) -> tuple[str, MediaKind]:
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", MediaKind.IMAGE
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", MediaKind.IMAGE
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return "image/webp", MediaKind.IMAGE
    if prefix.startswith(b"%PDF-"):
        return "application/pdf", MediaKind.DOCUMENT
    if prefix.startswith(b"wOF2"):
        return "font/woff2", MediaKind.FONT
    if prefix.startswith(b"OTTO"):
        return "font/otf", MediaKind.FONT
    if prefix.startswith(b"\x00\x01\x00\x00"):
        return "font/ttf", MediaKind.FONT
    if prefix.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm", MediaKind.VIDEO
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
        brand = prefix[8:12]
        if brand == b"qt  ":
            return "video/quicktime", MediaKind.VIDEO
        return "video/mp4", MediaKind.VIDEO
    text = prefix[:65_536].lstrip(b"\xef\xbb\xbf \t\r\n")
    lowered = text.lower()
    if lowered.startswith(b"<svg") or b"<svg" in lowered[:4_096]:
        return "image/svg+xml", MediaKind.VECTOR
    raise ValueError("UNSUPPORTED_OR_UNRECOGNIZED_MEDIA")


def sanitize_svg(payload: bytes) -> bytes:
    if len(payload) > 20 * 1024 * 1024:
        raise ValueError("SVG_TOO_LARGE")
    text = payload.decode("utf-8", errors="strict")
    if _SVG_FORBIDDEN_TEXT.search(text):
        raise ValueError("SVG_ACTIVE_CONTENT_REJECTED")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("SVG_PARSE_FAILED") from exc
    if not root.tag.lower().endswith("svg"):
        raise ValueError("SVG_ROOT_REQUIRED")
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1].casefold()
        if local in {"script", "foreignobject"}:
            raise ValueError("SVG_ACTIVE_CONTENT_REJECTED")
        for key, value in tuple(element.attrib.items()):
            attr = key.rsplit("}", 1)[-1].casefold()
            normalized = value.strip().casefold()
            if attr.startswith("on"):
                raise ValueError("SVG_EVENT_HANDLER_REJECTED")
            if attr in {"href", "src"} and normalized and not normalized.startswith("#"):
                raise ValueError("SVG_EXTERNAL_RESOURCE_REJECTED")
            if "javascript:" in normalized:
                raise ValueError("SVG_JAVASCRIPT_URL_REJECTED")
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


def basic_image_metadata(prefix: bytes, mime_type: str) -> dict[str, Any]:
    if mime_type == "image/png" and len(prefix) >= 26:
        width, height = struct.unpack(">II", prefix[16:24])
        color_type = prefix[25]
        return {"width": width, "height": height, "has_alpha": color_type in {4, 6}}
    if mime_type == "image/jpeg":
        index = 2
        while index + 9 < len(prefix):
            if prefix[index] != 0xFF:
                index += 1
                continue
            marker = prefix[index + 1]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(prefix[index + 5 : index + 7], "big")
                width = int.from_bytes(prefix[index + 7 : index + 9], "big")
                return {"width": width, "height": height, "has_alpha": False}
            if index + 4 > len(prefix):
                break
            segment_length = int.from_bytes(prefix[index + 2 : index + 4], "big")
            if segment_length < 2:
                break
            index += 2 + segment_length
    if mime_type == "image/webp" and len(prefix) >= 30:
        chunk = prefix[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(prefix[24:27], "little")
            height = 1 + int.from_bytes(prefix[27:30], "little")
            has_alpha = bool(prefix[20] & 0b0001_0000)
            return {"width": width, "height": height, "has_alpha": has_alpha}
    return {}


class FileScanner(Protocol):
    def scan(self, path: Path) -> FileScanResult: ...


class UnavailableFileScanner:
    def __init__(self, *, engine: str = "unavailable") -> None:
        self.engine = engine

    def scan(self, path: Path) -> FileScanResult:
        _ = path
        return FileScanResult(
            status=ScanStatus.UNAVAILABLE,
            engine=self.engine,
            detail="scanner unavailable",
        )


class ClamAVFileScanner:
    def __init__(self, command: str = "clamscan") -> None:
        self.command = command

    def scan(self, path: Path) -> FileScanResult:
        try:
            completed = subprocess.run(
                [self.command, "--no-summary", str(path)],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return FileScanResult(
                status=ScanStatus.UNAVAILABLE,
                engine="clamav",
                detail=type(exc).__name__,
            )
        output = (completed.stdout + completed.stderr).strip()
        if completed.returncode == 0:
            return FileScanResult(status=ScanStatus.CLEAN, engine="clamav")
        if completed.returncode == 1:
            signature = output.rsplit(":", 1)[-1].replace("FOUND", "").strip() or None
            return FileScanResult(
                status=ScanStatus.INFECTED,
                engine="clamav",
                signature=signature,
                detail="malware signature detected",
            )
        return FileScanResult(status=ScanStatus.ERROR, engine="clamav", detail=output[:1_000])


class MetadataExtractor(Protocol):
    def extract(self, path: Path, *, mime_type: str, prefix: bytes) -> dict[str, Any]: ...


class SafeMetadataExtractor:
    """Extracts a safe subset; GPS/EXIF raw blobs are intentionally never returned."""

    def __init__(self, ffprobe_command: str = "ffprobe") -> None:
        self.ffprobe_command = ffprobe_command

    def extract(self, path: Path, *, mime_type: str, prefix: bytes) -> dict[str, Any]:
        metadata = basic_image_metadata(prefix, mime_type)
        if mime_type.startswith("video/"):
            metadata.update(self._ffprobe(path))
        if mime_type.startswith("font/"):
            metadata["font_container"] = mime_type.split("/", 1)[1]
        return metadata

    def _ffprobe(self, path: Path) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                [
                    self.ffprobe_command,
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise ValueError("FFPROBE_UNAVAILABLE") from exc
        if completed.returncode != 0:
            raise ValueError("VIDEO_PARSE_FAILED")
        payload = json.loads(completed.stdout)
        streams = payload.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        if video is None:
            raise ValueError("VIDEO_STREAM_REQUIRED")
        result: dict[str, Any] = {
            "width": int(video.get("width", 0)) or None,
            "height": int(video.get("height", 0)) or None,
            "codec": video.get("codec_name"),
        }
        duration = video.get("duration") or payload.get("format", {}).get("duration")
        if duration is not None:
            result["duration_ms"] = max(0, int(float(duration) * 1000))
        rate = video.get("avg_frame_rate")
        if rate and rate != "0/0":
            numerator, denominator = rate.split("/", 1)
            if float(denominator):
                result["fps"] = float(numerator) / float(denominator)
        return {key: value for key, value in result.items() if value is not None}
