from __future__ import annotations

import asyncio
import json
import shutil
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont
from lumi_asset_storage import sanitize_svg, sniff_media_type
from PIL import Image, ImageOps


@dataclass(frozen=True, slots=True)
class PreviewOutput:
    variant: str
    preview_kind: str
    path: str
    mime_type: str
    width: int | None
    height: int | None


@dataclass(frozen=True, slots=True)
class MediaInspection:
    sniffed_mime_type: str
    kind: str
    width: int | None
    height: int | None
    metadata: dict[str, Any]
    sanitized_svg_path: str | None = None
    previews: tuple[PreviewOutput, ...] = ()


async def inspect_media(
    path: str,
    *,
    workspace: str,
    max_image_pixels: int,
    thumbnail_max_px: int,
    medium_max_px: int,
    ffprobe_command: str,
    ffmpeg_command: str,
) -> MediaInspection:
    prefix = Path(path).read_bytes()[:16384]
    sniffed = sniff_media_type(prefix)
    if sniffed.family == "image":
        return await asyncio.to_thread(
            _inspect_raster,
            path,
            workspace,
            sniffed.mime_type,
            max_image_pixels,
            thumbnail_max_px,
            medium_max_px,
        )
    if sniffed.mime_type == "image/svg+xml":
        return await asyncio.to_thread(_inspect_svg, path, workspace)
    if sniffed.family == "video":
        return await _inspect_video(
            path,
            workspace=workspace,
            mime_type=sniffed.mime_type,
            ffprobe_command=ffprobe_command,
            ffmpeg_command=ffmpeg_command,
            poster_max_px=medium_max_px,
        )
    if sniffed.family == "font":
        return await asyncio.to_thread(_inspect_font, path, sniffed.mime_type)
    if sniffed.mime_type == "application/pdf":
        return MediaInspection(
            sniffed_mime_type="application/pdf",
            kind="document",
            width=None,
            height=None,
            metadata={"format": "PDF"},
        )
    raise ValueError("UNSUPPORTED_MEDIA_TYPE")


def _inspect_raster(
    path: str,
    workspace: str,
    mime_type: str,
    max_image_pixels: int,
    thumbnail_max_px: int,
    medium_max_px: int,
) -> MediaInspection:
    previous_max = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = max_image_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as probe:
                probe.verify()
            with Image.open(path) as source:
                source = ImageOps.exif_transpose(source)
                width, height = source.size
                metadata: dict[str, Any] = {
                    "format": source.format,
                    "mode": source.mode,
                    "width": width,
                    "height": height,
                    "has_alpha": "A" in source.getbands(),
                }
                outputs: list[PreviewOutput] = []
                for variant, preview_kind, max_px in (
                    ("thumbnail", "thumbnail", thumbnail_max_px),
                    ("medium", "medium", medium_max_px),
                ):
                    preview = source.copy()
                    preview.thumbnail((max_px, max_px), Image.Resampling.LANCZOS)
                    if preview.mode not in {"RGB", "RGBA"}:
                        preview = preview.convert("RGBA" if "A" in preview.getbands() else "RGB")
                    output = Path(workspace) / f"{variant}.webp"
                    preview.save(output, "WEBP", quality=88, method=6, exif=b"")
                    outputs.append(
                        PreviewOutput(
                            variant=variant,
                            preview_kind=preview_kind,
                            path=str(output),
                            mime_type="image/webp",
                            width=preview.width,
                            height=preview.height,
                        )
                    )
                return MediaInspection(
                    sniffed_mime_type=mime_type,
                    kind="image",
                    width=width,
                    height=height,
                    metadata=metadata,
                    previews=tuple(outputs),
                )
    finally:
        Image.MAX_IMAGE_PIXELS = previous_max


def _inspect_svg(path: str, workspace: str) -> MediaInspection:
    raw = Path(path).read_bytes()
    cleaned = sanitize_svg(raw)
    sanitized = Path(workspace) / "sanitized.svg"
    sanitized.write_bytes(cleaned)
    return MediaInspection(
        sniffed_mime_type="image/svg+xml",
        kind="vector",
        width=None,
        height=None,
        metadata={"format": "SVG", "sanitized": True},
        sanitized_svg_path=str(sanitized),
    )


def _inspect_font(path: str, mime_type: str) -> MediaInspection:
    font = TTFont(path, lazy=True, recalcBBoxes=False, recalcTimestamp=False)
    try:
        names = font["name"] if "name" in font else None
        family = _font_name(names, 1) if names is not None else None
        subfamily = _font_name(names, 2) if names is not None else None
        full_name = _font_name(names, 4) if names is not None else None
        glyph_count = len(font.getGlyphOrder())
        return MediaInspection(
            sniffed_mime_type=mime_type,
            kind="font",
            width=None,
            height=None,
            metadata={
                "family": family,
                "subfamily": subfamily,
                "full_name": full_name,
                "glyph_count": glyph_count,
            },
        )
    finally:
        font.close()


def _font_name(name_table, name_id: int) -> str | None:
    for record in name_table.names:
        if record.nameID != name_id:
            continue
        try:
            value = record.toUnicode().strip()
        except Exception:
            continue
        if value:
            return value[:500]
    return None


async def _inspect_video(
    path: str,
    *,
    workspace: str,
    mime_type: str,
    ffprobe_command: str,
    ffmpeg_command: str,
    poster_max_px: int,
) -> MediaInspection:
    if shutil.which(ffprobe_command) is None:
        raise ValueError("FFPROBE_UNAVAILABLE")
    probe = await asyncio.create_subprocess_exec(
        ffprobe_command,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await probe.communicate()
    if probe.returncode != 0:
        raise ValueError("VIDEO_INVALID")
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("FFPROBE_OUTPUT_INVALID") from exc
    streams = payload.get("streams", [])
    video_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise ValueError("VIDEO_STREAM_REQUIRED")
    width = _positive_int(video_stream.get("width"))
    height = _positive_int(video_stream.get("height"))
    if width is None or height is None:
        raise ValueError("VIDEO_DIMENSIONS_INVALID")
    duration = payload.get("format", {}).get("duration")
    metadata = {
        "width": width,
        "height": height,
        "codec": video_stream.get("codec_name"),
        "pix_fmt": video_stream.get("pix_fmt"),
        "duration_seconds": float(duration) if duration is not None else None,
    }

    previews: tuple[PreviewOutput, ...] = ()
    if shutil.which(ffmpeg_command) is not None:
        poster_path = Path(workspace) / "poster.webp"
        scale = f"scale='min({poster_max_px},iw)':-2"
        process = await asyncio.create_subprocess_exec(
            ffmpeg_command,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            path,
            "-frames:v",
            "1",
            "-vf",
            scale,
            str(poster_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, _ = await process.communicate()
        if process.returncode == 0 and poster_path.exists():
            with Image.open(poster_path) as poster:
                previews = (
                    PreviewOutput(
                        variant="poster",
                        preview_kind="poster",
                        path=str(poster_path),
                        mime_type="image/webp",
                        width=poster.width,
                        height=poster.height,
                    ),
                )
    return MediaInspection(
        sniffed_mime_type=mime_type,
        kind="video",
        width=width,
        height=height,
        metadata=metadata,
        previews=previews,
    )


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
