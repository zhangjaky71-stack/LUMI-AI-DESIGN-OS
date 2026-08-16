from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from lumi_api.assets.ffmpeg_preview import FfmpegPreviewRenderer
from lumi_api.assets.models import AssetFileRole, MediaKind


def main() -> None:
    with tempfile.NamedTemporaryFile(suffix=".png") as source:
        completed = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=64x32:d=0.1",
                "-frames:v",
                "1",
                source.name,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr)
        renderer = FfmpegPreviewRenderer()
        previews = renderer.render(
            Path(source.name), media_kind=MediaKind.IMAGE, mime_type="image/png"
        )
        assert {preview.role for preview in previews} == {
            AssetFileRole.THUMBNAIL,
            AssetFileRole.MEDIUM,
        }
        assert all(preview.content.startswith(b"\x89PNG") for preview in previews)
    print("NODE18_FFMPEG_PREVIEW_PASS")


if __name__ == "__main__":
    main()
