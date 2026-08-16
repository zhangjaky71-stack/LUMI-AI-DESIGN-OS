from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..ssrf import ValidatedTarget


@dataclass(frozen=True, slots=True)
class MCPHTTPResponse:
    status: int
    headers: dict[str, str]
    json_body: dict[str, Any] | None
    content_type: str = "application/json"


class MCPHTTPTransport(Protocol):
    """Trusted HTTP port; implementation must connect to target.pinned_ip."""

    async def post(
        self,
        *,
        target: ValidatedTarget,
        headers: dict[str, str],
        body: dict[str, Any],
        timeout_seconds: float,
    ) -> MCPHTTPResponse: ...
