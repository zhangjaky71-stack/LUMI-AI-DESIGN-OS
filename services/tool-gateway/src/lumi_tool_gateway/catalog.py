from __future__ import annotations

from .contracts import ToolDefinition, ToolIdempotency, ToolRisk, ToolRuntime
from .registry import ToolRegistry

_OBJECT = {"type": "object"}
_UUID_BODY = (
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_UUID_PATTERN = rf"^{_UUID_BODY}$"
_ARTIFACT_REF_PATTERN = rf"^artifact://{_UUID_BODY}$"


def _uuid_schema() -> dict[str, object]:
    return {
        "type": "string",
        "minLength": 36,
        "maxLength": 36,
        "pattern": _UUID_PATTERN,
    }


def p0_tool_definitions() -> tuple[ToolDefinition, ...]:
    return (
        ToolDefinition(
            name="web.search",
            version="1.0.0",
            description="Search public web through an approved search backend.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["results"],
                "properties": {"results": {"type": "array", "maxItems": 20, "items": _OBJECT}},
                "additionalProperties": False,
            },
            risk=ToolRisk.READ_EXTERNAL,
            idempotency=ToolIdempotency.NOT_REQUIRED,
            permissions=frozenset({"tool.web.search"}),
            runtime=ToolRuntime.NATIVE,
            timeout_seconds=15,
        ),
        ToolDefinition(
            name="web.fetch",
            version="1.0.0",
            description="Fetch a public HTTP(S) resource through SSRF-controlled transport.",
            input_schema={
                "type": "object",
                "required": ["url"],
                "properties": {"url": {"type": "string", "minLength": 8, "maxLength": 4096}},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["url", "status", "content_type", "text"],
                "properties": {
                    "url": {"type": "string"},
                    "status": {"type": "integer"},
                    "content_type": {"type": "string"},
                    "text": {"type": "string"},
                },
                "additionalProperties": False,
            },
            risk=ToolRisk.READ_EXTERNAL,
            idempotency=ToolIdempotency.NOT_REQUIRED,
            permissions=frozenset({"tool.web.fetch"}),
            runtime=ToolRuntime.NATIVE,
            timeout_seconds=30,
            max_inline_output_bytes=96 * 1024,
        ),
        ToolDefinition(
            name="asset.read",
            version="1.0.0",
            description="Read tenant-scoped Asset metadata or a trusted resource reference.",
            input_schema={
                "type": "object",
                "required": ["asset_id"],
                "properties": {"asset_id": _uuid_schema()},
                "additionalProperties": False,
            },
            output_schema=_OBJECT,
            risk=ToolRisk.READ_INTERNAL,
            idempotency=ToolIdempotency.NOT_REQUIRED,
            permissions=frozenset({"tool.asset.read"}),
            runtime=ToolRuntime.NATIVE,
            timeout_seconds=10,
        ),
        ToolDefinition(
            name="asset.write-derived",
            version="1.0.0",
            description="Create a tenant-scoped derived Asset through the trusted storage boundary.",
            input_schema={
                "type": "object",
                "required": ["source_asset_id", "artifact_ref"],
                "properties": {
                    "source_asset_id": _uuid_schema(),
                    "artifact_ref": {
                        "type": "string",
                        "minLength": 47,
                        "maxLength": 47,
                        "pattern": _ARTIFACT_REF_PATTERN,
                    },
                    "metadata": _OBJECT,
                },
                "additionalProperties": False,
            },
            output_schema=_OBJECT,
            risk=ToolRisk.WRITE_INTERNAL,
            idempotency=ToolIdempotency.REQUIRED,
            permissions=frozenset({"tool.asset.write-derived"}),
            runtime=ToolRuntime.NATIVE,
            timeout_seconds=30,
        ),
        ToolDefinition(
            name="project.query",
            version="1.0.0",
            description="Read the canonical summary for the project bound to the current Task.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "enum": ["project.summary"],
                    }
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["project_id", "name", "status", "summary"],
                "properties": {
                    "project_id": _uuid_schema(),
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "summary": _OBJECT,
                },
                "additionalProperties": False,
            },
            risk=ToolRisk.READ_INTERNAL,
            idempotency=ToolIdempotency.NOT_REQUIRED,
            permissions=frozenset({"tool.project.query"}),
            runtime=ToolRuntime.NATIVE,
            timeout_seconds=10,
        ),
        ToolDefinition(
            name="artifact.query",
            version="1.0.0",
            description="Read Artifact metadata and resource references inside the tenant boundary.",
            input_schema={
                "type": "object",
                "required": ["artifact_id"],
                "properties": {"artifact_id": _uuid_schema()},
                "additionalProperties": False,
            },
            output_schema=_OBJECT,
            risk=ToolRisk.READ_INTERNAL,
            idempotency=ToolIdempotency.NOT_REQUIRED,
            permissions=frozenset({"tool.artifact.query"}),
            runtime=ToolRuntime.NATIVE,
            timeout_seconds=10,
        ),
        ToolDefinition(
            name="sandbox.execute",
            version="1.0.0",
            description="Execute an argv command through the isolated NODE-21 Sandbox service.",
            input_schema={
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 128,
                        "items": {"type": "string", "minLength": 1, "maxLength": 4096},
                    }
                },
                "additionalProperties": False,
            },
            output_schema=_OBJECT,
            risk=ToolRisk.WRITE_INTERNAL,
            idempotency=ToolIdempotency.REQUIRED,
            permissions=frozenset({"tool.sandbox.execute"}),
            runtime=ToolRuntime.SANDBOX,
            timeout_seconds=120,
            max_inline_output_bytes=64 * 1024,
        ),
        ToolDefinition(
            name="media.inspect",
            version="1.0.0",
            description="Inspect media metadata through an approved trusted adapter.",
            input_schema={
                "type": "object",
                "required": ["asset_id"],
                "properties": {"asset_id": _uuid_schema()},
                "additionalProperties": False,
            },
            output_schema=_OBJECT,
            risk=ToolRisk.READ_INTERNAL,
            idempotency=ToolIdempotency.NOT_REQUIRED,
            permissions=frozenset({"tool.media.inspect"}),
            runtime=ToolRuntime.NATIVE,
            timeout_seconds=20,
        ),
    )


def build_p0_registry() -> ToolRegistry:
    return ToolRegistry(p0_tool_definitions())
