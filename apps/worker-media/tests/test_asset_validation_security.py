from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lumi_worker_media.media_tools import inspect_media


@pytest.mark.asyncio
async def test_production_media_path_rejects_active_svg_content() -> None:
    payload = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<script>alert(1)</script>'
        b'</svg>'
    )
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.svg"
        source.write_bytes(payload)
        with pytest.raises(ValueError, match="SVG_ACTIVE_CONTENT_REJECTED"):
            await inspect_media(
                str(source),
                workspace=directory,
                max_image_pixels=40_000_000,
                thumbnail_max_px=512,
                medium_max_px=2048,
                ffprobe_command="ffprobe",
                ffmpeg_command="ffmpeg",
            )


@pytest.mark.asyncio
async def test_production_media_path_emits_sanitized_svg_derivative() -> None:
    payload = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b'<defs><path id="mark" d="M0 0 L10 10"/></defs>'
        b'<use href="#mark"/>'
        b'</svg>'
    )
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.svg"
        source.write_bytes(payload)
        result = await inspect_media(
            str(source),
            workspace=directory,
            max_image_pixels=40_000_000,
            thumbnail_max_px=512,
            medium_max_px=2048,
            ffprobe_command="ffprobe",
            ffmpeg_command="ffmpeg",
        )
        assert result.sniffed_mime_type == "image/svg+xml"
        assert result.sanitized_svg_path is not None
        sanitized = Path(result.sanitized_svg_path).read_bytes()
        assert b"script" not in sanitized.lower()
        assert b"#mark" in sanitized
