from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from ..contracts import ToolIdempotency, ToolRisk

MCP_PROTOCOL_2026_07_28 = "2026-07-28"
MCP_PROTOCOL_2025_11_25 = "2025-11-25"
_SERVER_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_MCP_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]{1,100}$")


class MCPProtocolEra(StrEnum):
    STATELESS_2026 = "stateless_2026"
    LEGACY_SESSION = "legacy_session"


class MCPTransportKind(StrEnum):
    STREAMABLE_HTTP = "streamable_http"
    LEGACY_HTTP_SSE = "legacy_http_sse"


class MCPTrustLevel(StrEnum):
    RESTRICTED = "restricted"
    ORGANIZATION_APPROVED = "organization_approved"
    PLATFORM_APPROVED = "platform_approved"


class MCPNetworkPolicy(StrEnum):
    PUBLIC_ONLY = "public_only"


@dataclass(frozen=True, slots=True)
class MCPClientIdentity:
    name: str = "lumi-ai-design-os"
    version: str = "1.0.0"
    capabilities: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 255:
            raise ValueError("MCP_CLIENT_NAME_INVALID")
        if not self.version or len(self.version) > 100:
            raise ValueError("MCP_CLIENT_VERSION_INVALID")
        if not isinstance(self.capabilities, dict):
            raise ValueError("MCP_CLIENT_CAPABILITIES_INVALID")


@dataclass(frozen=True, slots=True)
class MCPServerDefinition:
    server_id: str
    name: str
    base_url: str
    transport: MCPTransportKind
    enabled: bool
    approved: bool
    trust_level: MCPTrustLevel
    organization_id: UUID | None
    allowed_tool_patterns: tuple[str, ...]
    protocol_versions: tuple[str, ...]
    auth_profile: str | None = None
    auth_header_names: tuple[str, ...] = ("Authorization",)
    network_policy: MCPNetworkPolicy = MCPNetworkPolicy.PUBLIC_ONLY
    discovery_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not _SERVER_ID.fullmatch(self.server_id):
            raise ValueError("MCP_SERVER_ID_INVALID")
        if not self.name or len(self.name) > 255:
            raise ValueError("MCP_SERVER_NAME_INVALID")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MCP_SERVER_URL_INVALID")
        if parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise ValueError("MCP_SERVER_URL_INVALID")
        if not self.allowed_tool_patterns:
            raise ValueError("MCP_SERVER_TOOL_ALLOWLIST_REQUIRED")
        if not self.protocol_versions:
            raise ValueError("MCP_SERVER_PROTOCOL_VERSIONS_REQUIRED")
        for version in self.protocol_versions:
            if version not in {MCP_PROTOCOL_2026_07_28, MCP_PROTOCOL_2025_11_25}:
                raise ValueError(f"MCP_PROTOCOL_VERSION_UNSUPPORTED:{version}")
        normalized_headers: set[str] = set()
        for header in self.auth_header_names:
            if not _HEADER_NAME.fullmatch(header):
                raise ValueError("MCP_AUTH_HEADER_NAME_INVALID")
            lower = header.lower()
            if lower in normalized_headers:
                raise ValueError("MCP_AUTH_HEADER_NAME_DUPLICATE")
            normalized_headers.add(lower)
        if not 1 <= self.discovery_ttl_seconds <= 86_400:
            raise ValueError("MCP_DISCOVERY_TTL_INVALID")
        if self.auth_profile is not None and (
            not self.auth_profile or len(self.auth_profile) > 255
        ):
            raise ValueError("MCP_AUTH_PROFILE_INVALID")

    @property
    def protocol_era(self) -> MCPProtocolEra:
        if MCP_PROTOCOL_2026_07_28 in self.protocol_versions:
            return MCPProtocolEra.STATELESS_2026
        return MCPProtocolEra.LEGACY_SESSION


@dataclass(frozen=True, slots=True)
class MCPDiscoveredTool:
    remote_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _MCP_TOOL_NAME.fullmatch(self.remote_name):
            raise ValueError("MCP_TOOL_NAME_INVALID")
        if len(self.description) > 4000:
            raise ValueError("MCP_TOOL_DESCRIPTION_TOO_LARGE")
        if not isinstance(self.input_schema, dict):
            raise ValueError("MCP_TOOL_INPUT_SCHEMA_INVALID")
        if self.output_schema is not None and not isinstance(self.output_schema, dict):
            raise ValueError("MCP_TOOL_OUTPUT_SCHEMA_INVALID")
        if not isinstance(self.annotations, dict):
            raise ValueError("MCP_TOOL_ANNOTATIONS_INVALID")


@dataclass(frozen=True, slots=True)
class MCPToolPolicy:
    server_id: str
    remote_tool_name: str
    risk: ToolRisk
    permissions: frozenset[str]
    idempotency: ToolIdempotency
    description: str | None = None
    timeout_seconds: float = 30.0
    max_inline_output_bytes: int = 64 * 1024
    sensitive_fields: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not _SERVER_ID.fullmatch(self.server_id):
            raise ValueError("MCP_TOOL_POLICY_SERVER_INVALID")
        if not _MCP_TOOL_NAME.fullmatch(self.remote_tool_name):
            raise ValueError("MCP_TOOL_POLICY_NAME_INVALID")
        if not self.permissions:
            raise ValueError("MCP_TOOL_POLICY_PERMISSIONS_REQUIRED")
        if self.description is not None and (
            not self.description or len(self.description) > 2000
        ):
            raise ValueError("MCP_TOOL_POLICY_DESCRIPTION_INVALID")
        if self.risk in {
            ToolRisk.WRITE_INTERNAL,
            ToolRisk.WRITE_EXTERNAL,
            ToolRisk.DESTRUCTIVE,
            ToolRisk.FINANCIAL,
            ToolRisk.PRIVILEGED,
        } and self.idempotency != ToolIdempotency.REQUIRED:
            raise ValueError("MCP_WRITE_TOOL_IDEMPOTENCY_REQUIRED")
        if not 0.1 <= self.timeout_seconds <= 3600:
            raise ValueError("MCP_TOOL_TIMEOUT_INVALID")
        if not 1024 <= self.max_inline_output_bytes <= 1024 * 1024:
            raise ValueError("MCP_TOOL_OUTPUT_LIMIT_INVALID")


@dataclass(frozen=True, slots=True)
class MCPDiscoveryResult:
    protocol_version: str
    tools: tuple[MCPDiscoveredTool, ...]
    ttl_seconds: int
    cache_scope: str = "private"
    server_info: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MCPCallResult:
    structured_content: Any
    structured_content_present: bool
    content: tuple[dict[str, Any], ...]
    is_error: bool = False
    result_type: str = "complete"
    input_requests: dict[str, Any] | None = None
    request_state: str | None = None
