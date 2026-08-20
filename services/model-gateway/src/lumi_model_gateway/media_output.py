from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import ModelRequest


class ProviderBinaryOutputStore(Protocol):
    """Hosted storage port for provider-produced binary media.

    Small images may use bounded bytes. Large video must use the file-backed path
    so Model Gateway never materializes the complete provider video in Python heap.
    Provider adapters return only the opaque reference produced by this port.
    """

    async def store_bytes(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        data: bytes,
        content_type: str,
        extension: str,
    ) -> str: ...

    async def store_path(
        self,
        *,
        request: ModelRequest,
        provider: str,
        model: str,
        path: Path,
        content_type: str,
        extension: str,
        max_bytes: int,
    ) -> str: ...
