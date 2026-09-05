from __future__ import annotations

from ..errors import ToolGatewayError


class MCPError(ToolGatewayError):
    code = "MCP_ERROR"


class MCPServerUnavailableError(MCPError):
    code = "MCP_SERVER_UNAVAILABLE"


class MCPProtocolMismatchError(MCPError):
    code = "MCP_PROTOCOL_MISMATCH"


class MCPToolNotFoundError(MCPError):
    code = "MCP_TOOL_NOT_FOUND"


class MCPSchemaInvalidError(MCPError):
    code = "MCP_SCHEMA_INVALID"


class MCPAuthFailedError(MCPError):
    code = "MCP_AUTH_FAILED"


class MCPPolicyDeniedError(MCPError):
    code = "MCP_POLICY_DENIED"


class MCPInputRequiredError(MCPError):
    """Fail-closed bridge for MCP MRTR input_required results."""

    code = "MCP_INPUT_REQUIRED"

    def __init__(
        self,
        *,
        server_id: str,
        tool_name: str,
        request_keys: tuple[str, ...],
        request_state_present: bool,
    ) -> None:
        super().__init__(
            f"MCP input required for {server_id}/{tool_name}; "
            "resume through LUMI approval/input policy"
        )
        self.server_id = server_id
        self.tool_name = tool_name
        self.request_keys = request_keys
        self.request_state_present = request_state_present
