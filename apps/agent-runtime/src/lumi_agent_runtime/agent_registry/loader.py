from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .definition import AgentDefinition
from .errors import AgentDefinitionInvalidError
from .release_types import AgentReleaseManifest, AgentReleaseRecord, AgentReleaseStatus
from .requirements import MemoryPolicy, SkillRequirement, ToolRequirement

_REQUIRED = {
    "id",
    "version",
    "role",
    "description",
    "model_policy",
    "tools",
    "skills",
    "context_policy",
    "memory_policy",
    "budget_policy",
    "permissions",
    "output_schema",
    "eval_profile",
}
_ALLOWED = _REQUIRED | {"max_steps", "metadata"}


def load_definition(version_dir: Path) -> AgentDefinition:
    payload = _object(_read_json_yaml(version_dir / "agent.yaml"), "AGENT_DEFINITION_OBJECT_REQUIRED")
    missing = sorted(_REQUIRED - set(payload))
    unknown = sorted(set(payload) - _ALLOWED)
    if missing:
        raise AgentDefinitionInvalidError("missing AgentDefinition fields: " + ",".join(missing))
    if unknown:
        raise AgentDefinitionInvalidError("unknown AgentDefinition fields: " + ",".join(unknown))
    agent_id = _string(payload["id"], "AGENT_ID_REQUIRED")
    version = _string(payload["version"], "AGENT_VERSION_REQUIRED")
    if version_dir.name != version or version_dir.parent.name != agent_id:
        raise AgentDefinitionInvalidError("AgentDefinition path must match id/version")
    system_prompt = (version_dir / "system.md").read_text(encoding="utf-8")
    tools_raw = _object(payload["tools"], "AGENT_TOOLS_OBJECT_REQUIRED")
    if set(tools_raw) != {"allow"}:
        raise AgentDefinitionInvalidError("tools must contain only allow")
    tool_items = _list(tools_raw["allow"], "AGENT_TOOLS_ALLOW_LIST_REQUIRED")
    skills_raw = _list(payload["skills"], "AGENT_SKILLS_LIST_REQUIRED")
    memory_raw = _object(payload["memory_policy"], "AGENT_MEMORY_POLICY_OBJECT_REQUIRED")
    if not set(memory_raw) <= {"read", "write"}:
        raise AgentDefinitionInvalidError("memory_policy contains unknown fields")
    permissions_raw = _object(payload["permissions"], "AGENT_PERMISSIONS_OBJECT_REQUIRED")
    permissions: dict[str, bool] = {}
    for key, value in permissions_raw.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            raise AgentDefinitionInvalidError("permissions must map string to boolean")
        permissions[key] = value
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise AgentDefinitionInvalidError("metadata must be an object")
    try:
        return AgentDefinition(
            agent_id=agent_id,
            version=version,
            role=_string(payload["role"], "AGENT_ROLE_REQUIRED"),
            description=_string(payload["description"], "AGENT_DESCRIPTION_REQUIRED"),
            model_policy=_string(payload["model_policy"], "AGENT_MODEL_POLICY_REQUIRED"),
            tools=tuple(_tool(item) for item in tool_items),
            skills=tuple(SkillRequirement.parse(_string(item, "AGENT_SKILL_REF_REQUIRED")) for item in skills_raw),
            context_policy=_string(payload["context_policy"], "AGENT_CONTEXT_POLICY_REQUIRED"),
            memory_policy=MemoryPolicy(
                read=tuple(_strings(memory_raw.get("read", []), "AGENT_MEMORY_READ_INVALID")),
                write=tuple(_strings(memory_raw.get("write", []), "AGENT_MEMORY_WRITE_INVALID")),
            ),
            budget_policy=_string(payload["budget_policy"], "AGENT_BUDGET_POLICY_REQUIRED"),
            permissions=permissions,
            output_schema=_string(payload["output_schema"], "AGENT_OUTPUT_SCHEMA_REQUIRED"),
            eval_profile=_string(payload["eval_profile"], "AGENT_EVAL_PROFILE_REQUIRED"),
            system_prompt=system_prompt,
            max_steps=int(payload.get("max_steps", 64)),
            metadata=dict(metadata),
        )
    except (TypeError, ValueError) as exc:
        raise AgentDefinitionInvalidError(str(exc)) from exc


def load_definitions(agents_root: Path) -> tuple[AgentDefinition, ...]:
    rows: list[AgentDefinition] = []
    for agent_dir in sorted(path for path in agents_root.iterdir() if path.is_dir()):
        for version_dir in sorted(path for path in agent_dir.iterdir() if path.is_dir()):
            if (version_dir / "agent.yaml").exists():
                rows.append(load_definition(version_dir))
    return tuple(rows)


def load_release_manifest(path: Path) -> AgentReleaseManifest:
    payload = _object(_read_json_yaml(path), "AGENT_RELEASE_MANIFEST_OBJECT_REQUIRED")
    releases: list[AgentReleaseRecord] = []
    for raw in _list(payload.get("releases"), "AGENT_RELEASES_LIST_REQUIRED"):
        row = _object(raw, "AGENT_RELEASE_RECORD_OBJECT_REQUIRED")
        releases.append(
            AgentReleaseRecord(
                agent_id=_string(row.get("id"), "AGENT_RELEASE_ID_REQUIRED"),
                version=_string(row.get("version"), "AGENT_RELEASE_VERSION_REQUIRED"),
                status=AgentReleaseStatus(_string(row.get("status"), "AGENT_RELEASE_STATUS_REQUIRED")),
                eval_profile=_string(row.get("eval_profile"), "AGENT_RELEASE_EVAL_PROFILE_REQUIRED"),
                eval_status=row.get("eval_status") if isinstance(row.get("eval_status"), str) else None,
                eval_evidence=row.get("eval_evidence") if isinstance(row.get("eval_evidence"), str) else None,
                published_at=row.get("published_at") if isinstance(row.get("published_at"), str) else None,
            )
        )
    aliases_raw = _object(payload.get("aliases", {}), "AGENT_ALIASES_OBJECT_REQUIRED")
    aliases: dict[str, dict[str, str]] = {}
    for agent_id, raw in aliases_raw.items():
        aliases[str(agent_id)] = {
            str(alias): _string(version, "AGENT_ALIAS_VERSION_REQUIRED")
            for alias, version in _object(raw, "AGENT_ALIAS_MAP_REQUIRED").items()
        }
    return AgentReleaseManifest(
        schema=_string(payload.get("schema"), "AGENT_RELEASE_SCHEMA_REQUIRED"),
        revision=int(payload.get("revision", 0)),
        releases=tuple(releases),
        aliases=aliases,
    )


def _tool(value: Any) -> ToolRequirement:
    if isinstance(value, str):
        return ToolRequirement(name=value, version_constraint="1.x")
    raw = _object(value, "AGENT_TOOL_REQUIREMENT_INVALID")
    if not set(raw) <= {"name", "version"}:
        raise AgentDefinitionInvalidError("tool requirement contains unknown fields")
    return ToolRequirement(
        name=_string(raw.get("name"), "AGENT_TOOL_NAME_REQUIRED"),
        version_constraint=_string(raw.get("version", "1.x"), "AGENT_TOOL_VERSION_REQUIRED"),
    )


def _read_json_yaml(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentDefinitionInvalidError(f"invalid JSON-compatible YAML: {path}") from exc


def _object(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AgentDefinitionInvalidError(code)
    return value


def _list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise AgentDefinitionInvalidError(code)
    return value


def _string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise AgentDefinitionInvalidError(code)
    return value


def _strings(value: Any, code: str) -> list[str]:
    rows = _list(value, code)
    if not all(isinstance(item, str) and item for item in rows):
        raise AgentDefinitionInvalidError(code)
    return rows
