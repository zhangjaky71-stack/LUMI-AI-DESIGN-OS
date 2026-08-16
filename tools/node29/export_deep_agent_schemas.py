from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "nodes" / "NODE-29" / "generated-schemas"
DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _object(required: list[str], properties: dict) -> dict:
    return {
        "$schema": DRAFT,
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def schemas() -> dict[str, dict]:
    ref = {"type": "string", "pattern": r"^[a-z][a-z0-9+.-]*://"}
    string_array = {"type": "array", "items": {"type": "string"}}
    return {
        "permission-scope": _object(
            [
                "allowed_tools",
                "sandbox_execute",
                "memory_read_scopes",
                "memory_write_scopes",
                "allowed_subagents",
            ],
            {
                "allowed_tools": string_array,
                "sandbox_execute": {"type": "boolean"},
                "memory_read_scopes": string_array,
                "memory_write_scopes": string_array,
                "allowed_subagents": string_array,
            },
        ),
        "resolved-agent-config": _object(
            [
                "agent_id",
                "exact_version",
                "role",
                "model_profile",
                "allowed_tools",
                "skill_refs",
                "context_policy",
                "sandbox_execute",
                "output_schema",
                "content_hash",
            ],
            {
                "agent_id": {"type": "string"},
                "exact_version": {"type": "string"},
                "role": {"type": "string"},
                "model_profile": {"type": "string"},
                "allowed_tools": string_array,
                "skill_refs": string_array,
                "context_policy": {"type": "string"},
                "sandbox_execute": {"type": "boolean"},
                "output_schema": {"type": "string"},
                "content_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
            },
        ),
        "materialized-skill": _object(
            ["skill_id", "exact_version", "path", "content_hash"],
            {
                "skill_id": {"type": "string"},
                "exact_version": {"type": "string"},
                "path": {"type": "string", "pattern": "^/skills/"},
                "content_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "required_tools": string_array,
                "required_permissions": string_array,
                "provenance_ref": ref,
            },
        ),
        "pinned-context-bundle": _object(
            [
                "context_bundle_ref",
                "version",
                "pinned_constraints",
                "task_context",
                "source_refs",
                "content_hash",
            ],
            {
                "context_bundle_ref": ref,
                "version": {"type": "string"},
                "pinned_constraints": {"type": "string"},
                "task_context": {"type": "string"},
                "source_refs": {"type": "array", "items": ref},
                "content_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
            },
        ),
        "deep-agent-task-request": _object(
            ["agent_ref", "objective", "context_bundle_ref", "invocation"],
            {
                "agent_ref": {"type": "string"},
                "objective": {"type": "string"},
                "context_bundle_ref": ref,
                "invocation": {"type": "object"},
            },
        ),
        "agent-task-result": _object(
            [
                "status",
                "summary",
                "decisions",
                "artifact_refs",
                "knowledge_refs",
                "proposed_operations",
                "open_questions",
                "confidence",
            ],
            {
                "status": {
                    "type": "string",
                    "enum": ["succeeded", "partial", "needs_input", "failed"],
                },
                "summary": {"type": "string"},
                "decisions": string_array,
                "artifact_refs": {"type": "array", "items": ref},
                "knowledge_refs": {"type": "array", "items": ref},
                "proposed_operations": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "open_questions": string_array,
                "confidence": {"type": ["string", "number"]},
            },
        ),
        "deep-agent-provenance": _object(
            [
                "agent_id",
                "agent_version",
                "agent_config_hash",
                "context_bundle_ref",
                "context_hash",
                "skill_versions",
                "tool_versions",
                "model_profile",
                "sandbox_execute",
            ],
            {
                "agent_id": {"type": "string"},
                "agent_version": {"type": "string"},
                "agent_config_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "context_bundle_ref": ref,
                "context_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "skill_versions": string_array,
                "tool_versions": string_array,
                "model_profile": {"type": "string"},
                "sandbox_execute": {"type": "boolean"},
            },
        ),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for existing in OUT.glob("*.schema.json"):
        existing.unlink()
    for name, schema in schemas().items():
        path = OUT / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"exported {len(schemas())} NODE-29 schemas")


if __name__ == "__main__":
    main()
