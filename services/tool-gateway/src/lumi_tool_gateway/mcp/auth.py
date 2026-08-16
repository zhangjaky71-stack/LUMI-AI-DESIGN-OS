from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .contracts import MCPServerDefinition
from .errors import MCPAuthFailedError

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
    organization_id: UUID
    server_id: str
    headers: dict[str, str]
    subject: str | None = None
    expires_at_epoch: int | None = None

    def __post_init__(self) -> None:
        if not self.server_id or len(self.server_id) > 63:
            raise ValueError("MCP_AUTH_SERVER_ID_INVALID")
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
        if self.expires_at_epoch is not None and self.expires_at_epoch <= 0:
            raise ValueError("MCP_AUTH_EXPIRY_INVALID")


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
        return MCPRequestAuth(
            organization_id=organization_id,
            server_id=server.server_id,
            headers={},
        )


def validate_request_auth(
    server: MCPServerDefinition,
    *,
    organization_id: UUID,
    auth: MCPRequestAuth,
    now_epoch: int | None = None,
) -> None:
    if auth.organization_id != organization_id:
        raise MCPAuthFailedError("MCP credential tenant mismatch")
    if auth.server_id != server.server_id:
        raise MCPAuthFailedError("MCP credential server mismatch")
    if auth.headers and server.auth_profile is None:
        raise MCPAuthFailedError("MCP credential supplied for no-auth server")
    allowed = {header.lower() for header in server.auth_header_names}
    unexpected = {header.lower() for header in auth.headers} - allowed
    if unexpected:
        raise MCPAuthFailedError("MCP credential returned unapproved auth header")
    if auth.expires_at_epoch is not None:
        current = int(time.time()) if now_epoch is None else now_epoch
        if auth.expires_at_epoch <= current:
            raise MCPAuthFailedError("MCP credential expired")
