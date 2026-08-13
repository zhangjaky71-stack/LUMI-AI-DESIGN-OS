from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .contracts import MCPServerDefinition

_RESERVED_HEADERS = frozenset(
    {
        "host",
        "cookie",
        "mcp-protocol-version",
        "mcp-method",
        "mcp-name",
        "mcp-session-id",
        "content-type",
        "accept",
    }
)


@dataclass(frozen=True, slots=True)
class MCPRequestAuth:
    headers: dict[str, str]
    subject: str | None = None
    expires_at_epoch: int | None = None

    def __post_init__(self) -> None:
        normalized: set[str] = set()
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in _RESERVED_HEADERS:
                raise ValueError(f"MCP_AUTH_RESERVED_HEADER:{key}")
            if lower in normalized:
                raise ValueError(f"MCP_AUTH_DUPLICATE_HEADER:{key}")
            if not key or "\r" in key or "\n" in key:
                raise ValueError("MCP_AUTH_HEADER_INVALID")
            if "\r" in value or "\n" in value:
                raise ValueError("MCP_AUTH_HEADER_INVALID")
            normalized.add(lower)
        if self.subject is not None and len(self.subject) > 512:
            raise ValueError("MCP_AUTH_SUBJECT_INVALID")


class MCPCredentialProvider(Protocol):
    async def credentials_for(
        self,
        server: MCPServerDefinition,
        *,
        organization_id: UUID,
    ) -> MCPRequestAuth: ...


class NoAuthCredentialProvider:
    async def credentials_for(
        self,
        server: MCPServerDefinition,
        *,
        organization_id: UUID,
    ) -> MCPRequestAuth:
        del server, organization_id
        return MCPRequestAuth(headers={})
