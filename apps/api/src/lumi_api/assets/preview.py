from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import AssetFileRole, MediaKind, PreviewResult


class PreviewRenderer(Protocol):
    def render(
        self,
        path: Path,
        *,
        media_kind: MediaKind,
        mime_type: str,
    ) -> tuple[PreviewResult, ...]: ...


class NoopPreviewRenderer:
    def render(
        self,
        path: Path,
        *,
        media_kind: MediaKind,
        mime_type: str,
    ) -> tuple[PreviewResult, ...]:
        _ = (path, media_kind, mime_type)
        return ()


class DeterministicPreviewRenderer:
    """Test/reference adapter proving the preview pipeline contract without provider SDKs."""

    def render(
        self,
        path: Path,
        *,
        media_kind: MediaKind,
        mime_type: str,
    ) -> tuple[PreviewResult, ...]:
        payload = path.read_bytes()
        if media_kind not in {MediaKind.IMAGE, MediaKind.VIDEO, MediaKind.DOCUMENT, MediaKind.VECTOR}:
            return ()
        marker = b"LUMI_PREVIEW_V1\n" + mime_type.encode() + b"\n" + payload[:4096]
        if media_kind == MediaKind.VIDEO:
            return (
                PreviewResult(
                    role=AssetFileRole.POSTER,
                    mime_type="application/octet-stream",
                    content=marker,
                ),
            )
        return (
            PreviewResult(
                role=AssetFileRole.THUMBNAIL,
                mime_type="application/octet-stream",
                content=marker + b"\nthumbnail",
            ),
            PreviewResult(
                role=AssetFileRole.MEDIUM,
                mime_type="application/octet-stream",
                content=marker + b"\nmedium",
            ),
        )
