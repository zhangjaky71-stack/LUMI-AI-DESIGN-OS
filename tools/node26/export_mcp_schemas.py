from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/nodes/NODE-26/generated-schemas"

UUID = {"type": "string", "format": "uuid"}
JSON_OBJECT = {"type": "object"}


def object_schema(properties, required):
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def schemas() -> dict[str, dict]:
    server = object_schema(
        {
            "server_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,62}$"},
            "name": {"type": "string", "minLength": 1, "maxLength": 255},
            "base_url": {"type": "string", "pattern": "^https://"},
            "transport": {"enum": ["streamable_http", "legacy_http_sse"]},
            "enabled": {"type": "boolean"},
            "approved": {"type": "boolean"},
            "trust_level": {
                "enum": ["restricted", "organization_approved", "platform_approved"]
            },
            "organization_id": {"anyOf": [UUID, {"type": "null"}]},
            "allowed_tool_patterns": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "protocol_versions": {
                "type": "array",
                "minItems": 1,
                "items": {"enum": ["2026-07-28", "2025-11-25"]},
            },
            "auth_profile": {"type": ["string", "null"]},
            "auth_header_names": {"type": "array", "items": {"type": "string"}},
            "network_policy": {"const": "public_only"},
            "discovery_ttl_seconds": {"type": "integer", "minimum": 1, "maximum": 86400},
        },
        [
            "server_id",
            "name",
            "base_url",
            "transport",
            "enabled",
            "approved",
            "trust_level",
            "organization_id",
            "allowed_tool_patterns",
            "protocol_versions",
        ],
    )
    policy = object_schema(
        {
            "server_id": {"type": "string"},
            "remote_tool_name": {"type": "string", "minLength": 1, "maxLength": 128},
            "risk": {
                "enum": [
                    "READ_INTERNAL",
                    "READ_EXTERNAL",
                    "WRITE_INTERNAL",
                    "WRITE_EXTERNAL",
                    "DESTRUCTIVE",
                    "FINANCIAL",
                    "PRIVILEGED",
                ]
            },
            "permissions": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "idempotency": {"enum": ["NOT_REQUIRED", "REQUIRED"]},
            "description": {"type": ["string", "null"]},
            "timeout_seconds": {"type": "number", "minimum": 0.1, "maximum": 3600},
            "max_inline_output_bytes": {
                "type": "integer",
                "minimum": 1024,
                "maximum": 1048576,
            },
            "sensitive_fields": {"type": "array", "items": {"type": "string"}},
        },
        ["server_id", "remote_tool_name", "risk", "permissions", "idempotency"],
    )
    discovered = object_schema(
        {
            "remote_name": {"type": "string", "minLength": 1, "maxLength": 128},
            "description": {"type": "string", "maxLength": 4000},
            "input_schema": JSON_OBJECT,
            "output_schema": {"anyOf": [JSON_OBJECT, {"type": "null"}]},
            "annotations": JSON_OBJECT,
        },
        ["remote_name", "description", "input_schema"],
    )
    discovery = object_schema(
        {
            "protocol_version": {"enum": ["2026-07-28", "2025-11-25"]},
            "tools": {"type": "array", "items": discovered},
            "ttl_seconds": {"type": "integer", "minimum": 0, "maximum": 86400},
            "cache_scope": {"enum": ["private", "public"]},
            "server_info": JSON_OBJECT,
        },
        ["protocol_version", "tools", "ttl_seconds"],
    )
    request_auth = object_schema(
        {
            "organization_id": UUID,
            "server_id": {"type": "string", "minLength": 1, "maxLength": 63},
            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "subject": {"type": ["string", "null"], "maxLength": 512},
            "expires_at_epoch": {"type": ["integer", "null"], "minimum": 1},
        },
        ["organization_id", "server_id", "headers"],
    )
    call_result = object_schema(
        {
            "structured_content": {},
            "structured_content_present": {"type": "boolean"},
            "content": {"type": "array", "items": JSON_OBJECT},
            "is_error": {"type": "boolean"},
            "result_type": {"type": "string", "minLength": 1},
            "input_requests": {"anyOf": [JSON_OBJECT, {"type": "null"}]},
            "request_state": {"type": ["string", "null"]},
        },
        ["structured_content_present", "content", "result_type"],
    )
    return {
        "mcp-server-definition.schema.json": server,
        "mcp-tool-policy.schema.json": policy,
        "mcp-discovered-tool.schema.json": discovered,
        "mcp-discovery-result.schema.json": discovery,
        "mcp-request-auth.schema.json": request_auth,
        "mcp-call-result.schema.json": call_result,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.schema.json"):
        old.unlink()
    items = schemas()
    for name, schema in sorted(items.items()):
        (OUT / name).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"NODE26_MCP_SCHEMAS_EXPORTED={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
