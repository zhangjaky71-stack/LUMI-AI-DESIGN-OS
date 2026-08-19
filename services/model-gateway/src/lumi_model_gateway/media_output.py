from __future__ import annotations

from typing import Protocol

from .models import ModelRequest


class ProviderBinaryOutputStore(Protocol):
    """Hosted storage port for provider-produced binary media.

    Provider adapters may return only the opaque reference produced by this port;
    raw image/video bytes must never escape into Model Gateway JSON or queue payloads.
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
