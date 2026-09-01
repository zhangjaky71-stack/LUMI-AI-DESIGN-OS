from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import ModelRequest


class ProviderBinaryOutputStore(Protocol):
    """Hosted storage port for provider-produced binary media.

    Small synchronous images may use bounded bytes. Large video uses file-backed
    staging. Async jobs additionally have a provider-job identity path so status
    recovery remains valid after a Model Gateway process restart, when the original
    ModelRequest is no longer resident in memory.
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

    async def store_async_path(
        self,
        *,
        provider: str,
        model: str,
        provider_request_id: str,
        path: Path,
        content_type: str,
        extension: str,
        max_bytes: int,
    ) -> str: ...
