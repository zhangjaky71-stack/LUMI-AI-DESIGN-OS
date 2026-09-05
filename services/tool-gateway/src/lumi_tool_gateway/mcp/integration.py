from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ..contracts import ToolDefinition
from ..ports import ToolAdapter
from .adapter import MCPToolAdapter
from .client import MCPClient
from .contracts import MCPToolPolicy
from .mapping import MCPToolMapper, mcp_lumi_tool_name


@dataclass(frozen=True, slots=True)
class MCPIntegrationPlan:
    server_id: str
    protocol_version: str
    definitions: tuple[ToolDefinition, ...]
    adapters: dict[str, ToolAdapter]


class MCPIntegrationBuilder:
    """Produces only admin-approved ToolDefinitions/Adapters after discovery."""

    def __init__(
        self,
        *,
        client: MCPClient,
        mapper: MCPToolMapper | None = None,
    ) -> None:
        self.client = client
        self.mapper = mapper or MCPToolMapper()

    async def prepare(
        self,
        server_id: str,
        *,
        organization_id: UUID,
        policies: tuple[MCPToolPolicy, ...],
        force_discovery: bool = False,
    ) -> MCPIntegrationPlan:
        server = self.client.registry.resolve(
            server_id,
            organization_id=organization_id,
        )
        discovery = await self.client.discover_tools(
            server_id,
            organization_id=organization_id,
            force=force_discovery,
        )
        definitions = self.mapper.map_approved_tools(
            server=server,
            discovered=discovery.tools,
            policies=policies,
        )
        remote_by_lumi = {
            mcp_lumi_tool_name(server.server_id, tool.remote_name): tool.remote_name
            for tool in discovery.tools
        }
        adapters: dict[str, ToolAdapter] = {}
        for definition in definitions:
            remote_name = remote_by_lumi[definition.name]
            adapters[definition.key] = MCPToolAdapter(
                client=self.client,
                server_id=server.server_id,
                remote_tool_name=remote_name,
                lumi_tool_name=definition.name,
                protocol_version=discovery.protocol_version,
            )
        return MCPIntegrationPlan(
            server_id=server.server_id,
            protocol_version=discovery.protocol_version,
            definitions=definitions,
            adapters=adapters,
        )
