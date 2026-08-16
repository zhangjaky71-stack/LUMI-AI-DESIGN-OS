from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports/nodes/NODE-25/generated-schemas"
DRAFT = "https://json-schema.org/draft/2020-12/schema"


def object_schema(
    title: str,
    properties: dict[str, object],
    required: list[str],
) -> dict[str, object]:
    return {
        "$schema": DRAFT,
        "title": title,
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


SCHEMAS: dict[str, dict[str, object]] = {
    "tool-definition": object_schema(
        "ToolDefinition",
        {
            "name": {"type": "string"},
            "version": {"type": "string"},
            "description": {"type": "string"},
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
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
            "idempotency": {"enum": ["NOT_REQUIRED", "REQUIRED"]},
            "permissions": {"type": "array", "items": {"type": "string"}},
            "runtime": {"enum": ["native", "mcp", "sandbox"]},
            "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
            "max_inline_output_bytes": {"type": "integer", "minimum": 1024},
        },
        [
            "name",
            "version",
            "description",
            "input_schema",
            "output_schema",
            "risk",
            "idempotency",
            "permissions",
            "runtime",
        ],
    ),
    "tool-permission-context": object_schema(
        "ToolPermissionContext",
        {
            "organization_id": {"type": "string", "format": "uuid"},
            "actor_id": {"type": "string"},
            "granted_permissions": {"type": "array", "items": {"type": "string"}},
            "agent_allow_patterns": {"type": "array", "items": {"type": "string"}},
            "parent_allow_patterns": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "organization_allow_patterns": {
                "type": "array",
                "items": {"type": "string"},
            },
            "organization_deny_patterns": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        [
            "organization_id",
            "actor_id",
            "granted_permissions",
            "agent_allow_patterns",
        ],
    ),
    "tool-request": object_schema(
        "ToolRequest",
        {
            "tool_call_id": {"type": "string", "format": "uuid"},
            "organization_id": {"type": "string", "format": "uuid"},
            "agent_run_id": {"type": "string", "format": "uuid"},
            "task_id": {"type": "string", "format": "uuid"},
            "actor_agent": {"type": "string"},
            "name": {"type": "string"},
            "version": {"type": "string"},
            "arguments": {"type": "object"},
            "purpose": {"type": "string"},
            "idempotency_key": {"type": ["string", "null"], "maxLength": 255},
            "approval_token": {"type": ["string", "null"]},
            "trace_id": {"type": ["string", "null"]},
        },
        [
            "tool_call_id",
            "organization_id",
            "agent_run_id",
            "task_id",
            "actor_agent",
            "name",
            "version",
            "arguments",
            "purpose",
        ],
    ),
    "tool-result": object_schema(
        "ToolResult",
        {
            "tool_call_id": {"type": "string", "format": "uuid"},
            "status": {
                "enum": ["SUCCEEDED", "APPROVAL_REQUIRED", "DENIED", "FAILED"]
            },
            "resolved_name": {"type": "string"},
            "resolved_version": {"type": "string"},
            "summary": {"type": "string"},
            "data": {},
            "resource_refs": {"type": "array", "items": {"type": "string"}},
            "truncated": {"type": "boolean"},
            "full_result_ref": {"type": ["string", "null"]},
            "replayed": {"type": "boolean"},
            "approval_id": {"type": ["string", "null"]},
            "error_code": {"type": ["string", "null"]},
        },
        ["tool_call_id", "status", "resolved_name", "resolved_version"],
    ),
    "tool-audit-record": object_schema(
        "ToolAuditRecord",
        {
            "tool_call_id": {"type": "string"},
            "organization_id": {"type": "string"},
            "actor_id": {"type": "string"},
            "actor_agent": {"type": "string"},
            "resolved_tool": {"type": "string"},
            "risk": {"type": "string"},
            "purpose": {"type": "string"},
            "status": {"type": "string"},
            "trace_id": {"type": ["string", "null"]},
            "arguments": {"type": "object"},
            "replayed": {"type": "boolean"},
            "side_effect_operation_id": {"type": ["string", "null"]},
            "approval_id": {"type": ["string", "null"]},
            "error_code": {"type": ["string", "null"]},
        },
        [
            "tool_call_id",
            "organization_id",
            "actor_id",
            "actor_agent",
            "resolved_tool",
            "risk",
            "purpose",
            "status",
            "arguments",
        ],
    ),
    "tool-side-effect-context": object_schema(
        "ToolSideEffectContext",
        {
            "organization_id": {"type": "string", "format": "uuid"},
            "operation_type": {"type": "string", "maxLength": 100},
            "idempotency_key": {"type": "string", "maxLength": 255},
            "request": {"type": "object"},
            "business_scope_id": {"type": "string", "format": "uuid"},
        },
        [
            "organization_id",
            "operation_type",
            "idempotency_key",
            "request",
            "business_scope_id",
        ],
    ),
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT.glob("*.schema.json"):
        path.unlink()
    for name, schema in sorted(SCHEMAS.items()):
        (OUTPUT / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"NODE25_TOOL_SCHEMAS_EXPORTED={len(SCHEMAS)}")


if __name__ == "__main__":
    main()
