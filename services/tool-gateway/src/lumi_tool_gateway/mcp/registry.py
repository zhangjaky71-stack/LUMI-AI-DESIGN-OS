from __future__ import annotations

import fnmatch
from uuid import UUID

from ..ssrf import SSRFPolicy, ValidatedTarget
from .contracts import (
    MCP_PROTOCOL_2025_11_25,
    MCP_PROTOCOL_2026_07_28,
    MCPServerDefinition,
)
from .errors import MCPPolicyDeniedError, MCPProtocolMismatchError


class MCPServerRegistry:
    """Admin-approved MCP server catalog; arbitrary Agent URLs never enter this API."""

    def __init__(
        self,
        definitions: tuple[MCPServerDefinition, ...] = (),
        *,
        ssrf_policy: SSRFPolicy | None = None,
    ) -> None:
        self.ssrf_policy = ssrf_policy or SSRFPolicy()
        self._servers: dict[str, MCPServerDefinition] = {}
        self._validated_targets: dict[str, ValidatedTarget] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: MCPServerDefinition) -> None:
        if definition.server_id in self._servers:
            raise ValueError(f"MCP_SERVER_DUPLICATE:{definition.server_id}")
        target = self.ssrf_policy.validate(definition.base_url)
        self._servers[definition.server_id] = definition
        self._validated_targets[definition.server_id] = target

    def resolve(
        self,
        server_id: str,
        *,
        organization_id: UUID,
    ) -> MCPServerDefinition:
        try:
            definition = self._servers[server_id]
        except KeyError as exc:
            raise MCPPolicyDeniedError("MCP_SERVER_NOT_REGISTERED") from exc
        if not definition.approved:
            raise MCPPolicyDeniedError("MCP_SERVER_NOT_APPROVED")
        if not definition.enabled:
            raise MCPPolicyDeniedError("MCP_SERVER_DISABLED")
        if (
            definition.organization_id is not None
            and definition.organization_id != organization_id
        ):
            raise MCPPolicyDeniedError("MCP_SERVER_TENANT_DENIED")
        return definition

    def validated_target(
        self,
        server_id: str,
        *,
        organization_id: UUID,
    ) -> ValidatedTarget:
        self.resolve(server_id, organization_id=organization_id)
        return self._validated_targets[server_id]

    def negotiate_protocol(
        self,
        definition: MCPServerDefinition,
        server_supported: tuple[str, ...] | None = None,
    ) -> str:
        supported = set(server_supported or definition.protocol_versions)
        configured = set(definition.protocol_versions)
        mutual = supported & configured
        if MCP_PROTOCOL_2026_07_28 in mutual:
            return MCP_PROTOCOL_2026_07_28
        if MCP_PROTOCOL_2025_11_25 in mutual:
            return MCP_PROTOCOL_2025_11_25
        raise MCPProtocolMismatchError("no mutually supported MCP protocol version")

    @staticmethod
    def tool_allowed(definition: MCPServerDefinition, remote_tool_name: str) -> bool:
        return any(
            fnmatch.fnmatchcase(remote_tool_name, pattern)
            for pattern in definition.allowed_tool_patterns
        )

    def definitions(self) -> tuple[MCPServerDefinition, ...]:
        return tuple(self._servers[key] for key in sorted(self._servers))
