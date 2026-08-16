from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .models import AssetFileRole, MediaKind, PreviewResult


class FfmpegPreviewRenderer:
    """Reference production adapter for raster images and video poster/preview frames."""

    def __init__(self, command: str = "ffmpeg") -> None:
        self.command = command

    def _render_png(self, path: Path, *, max_width: int, seek: bool) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png") as target:
            command = [self.command, "-v", "error", "-y"]
            if seek:
                command.extend(["-ss", "0.5"])
            command.extend(
                [
                    "-i",
                    str(path),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale='min({max_width},iw)':-2",
                    target.name,
                ]
            )
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise ValueError("FFMPEG_PREVIEW_UNAVAILABLE") from exc
            if completed.returncode != 0:
                raise ValueError("FFMPEG_PREVIEW_FAILED")
            target.seek(0)
            return target.read()

    def render(
        self,
        path: Path,
        *,
        media_kind: MediaKind,
        mime_type: str,
    ) -> tuple[PreviewResult, ...]:
        _ = mime_type
        if media_kind is MediaKind.IMAGE:
            return (
                PreviewResult(
                    role=AssetFileRole.THUMBNAIL,
                    mime_type="image/png",
                    content=self._render_png(path, max_width=320, seek=False),
                ),
                PreviewResult(
                    role=AssetFileRole.MEDIUM,
                    mime_type="image/png",
                    content=self._render_png(path, max_width=1280, seek=False),
                ),
            )
        if media_kind is MediaKind.VIDEO:
            return (
                PreviewResult(
                    role=AssetFileRole.POSTER,
                    mime_type="image/png",
                    content=self._render_png(path, max_width=1280, seek=True),
                ),
            )
        return ()
