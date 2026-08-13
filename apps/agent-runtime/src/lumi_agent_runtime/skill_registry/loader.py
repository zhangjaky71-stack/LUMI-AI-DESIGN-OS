from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lumi_agent_runtime.agent_registry.requirements import SkillRequirement, ToolRequirement

from .contracts import (
    SkillDefinition,
    SkillReleaseManifest,
    SkillReleaseRecord,
    SkillReleaseStatus,
)
from .errors import SkillDefinitionInvalidError


def load_skill(version_dir: Path) -> SkillDefinition:
    payload = _object(
        _read_json(version_dir / "skill.yaml"),
        "SKILL_DEFINITION_OBJECT_REQUIRED",
    )
    if (
        payload.get("id") != version_dir.parent.name
        or payload.get("version") != version_dir.name
    ):
        raise SkillDefinitionInvalidError("Skill path must match id/version")
    markdown = (version_dir / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = _frontmatter(markdown)
    if frontmatter.get("name") != payload.get("id"):
        raise SkillDefinitionInvalidError(
            "SKILL.md frontmatter name must match Skill id"
        )
    if frontmatter.get("description") != payload.get("summary"):
        raise SkillDefinitionInvalidError(
            "SKILL.md description must match skill summary"
        )
    resources: dict[str, str] = {}
    for path in sorted(version_dir.rglob("*")):
        if not path.is_file() or path.name in {"skill.yaml", "SKILL.md"}:
            continue
        relative = path.relative_to(version_dir).as_posix()
        try:
            resources[relative] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SkillDefinitionInvalidError(
                f"Skill resources must be UTF-8 text: {relative}"
            ) from exc
    try:
        return SkillDefinition(
            skill_id=_string(payload.get("id"), "SKILL_ID_REQUIRED"),
            version=_string(payload.get("version"), "SKILL_VERSION_REQUIRED"),
            summary=_string(payload.get("summary"), "SKILL_SUMMARY_REQUIRED"),
            compatible_agents=tuple(
                _strings(
                    payload.get("compatible_agents"),
                    "SKILL_COMPATIBLE_AGENTS_REQUIRED",
                )
            ),
            required_tools=tuple(
                _tool(item)
                for item in _list(
                    payload.get("required_tools", []),
                    "SKILL_REQUIRED_TOOLS_INVALID",
                )
            ),
            required_capabilities=tuple(
                _strings(
                    payload.get("required_capabilities", []),
                    "SKILL_CAPABILITIES_INVALID",
                )
            ),
            input_schema=_string(
                payload.get("input_schema"),
                "SKILL_INPUT_SCHEMA_REQUIRED",
            ),
            output_schema=_string(
                payload.get("output_schema"),
                "SKILL_OUTPUT_SCHEMA_REQUIRED",
            ),
            permissions=tuple(
                _strings(
                    payload.get("permissions", []),
                    "SKILL_PERMISSIONS_INVALID",
                )
            ),
            dependencies=tuple(
                SkillRequirement.parse(
                    _string(item, "SKILL_DEPENDENCY_INVALID")
                )
                for item in _list(
                    payload.get("dependencies", []),
                    "SKILL_DEPENDENCIES_INVALID",
                )
            ),
            eval_profile=_string(
                payload.get("eval_profile"),
                "SKILL_EVAL_PROFILE_REQUIRED",
            ),
            task_types=tuple(
                _strings(
                    payload.get("task_types", []),
                    "SKILL_TASK_TYPES_INVALID",
                )
            ),
            skill_markdown=markdown,
            resources=resources,
            metadata=dict(
                _object(
                    payload.get("metadata", {}),
                    "SKILL_METADATA_INVALID",
                )
            ),
        )
    except (TypeError, ValueError) as exc:
        raise SkillDefinitionInvalidError(str(exc)) from exc


def load_skills(root: Path) -> tuple[SkillDefinition, ...]:
    rows: list[SkillDefinition] = []
    for skill_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        for version_dir in sorted(path for path in skill_dir.iterdir() if path.is_dir()):
            if (version_dir / "skill.yaml").exists():
                rows.append(load_skill(version_dir))
    return tuple(rows)


def load_release_manifest(path: Path) -> SkillReleaseManifest:
    payload = _object(_read_json(path), "SKILL_RELEASE_MANIFEST_INVALID")
    releases = tuple(
        SkillReleaseRecord(
            skill_id=_string(row.get("id"), "SKILL_RELEASE_ID_REQUIRED"),
            version=_string(row.get("version"), "SKILL_RELEASE_VERSION_REQUIRED"),
            status=SkillReleaseStatus(
                _string(row.get("status"), "SKILL_RELEASE_STATUS_REQUIRED")
            ),
            eval_profile=_string(
                row.get("eval_profile"),
                "SKILL_RELEASE_EVAL_REQUIRED",
            ),
            eval_status=(
                row.get("eval_status")
                if isinstance(row.get("eval_status"), str)
                else None
            ),
            eval_evidence=(
                row.get("eval_evidence")
                if isinstance(row.get("eval_evidence"), str)
                else None
            ),
        )
        for row in (
            _object(item, "SKILL_RELEASE_RECORD_INVALID")
            for item in _list(payload.get("releases"), "SKILL_RELEASES_REQUIRED")
        )
    )
    aliases = {
        str(skill_id): {
            str(alias): _string(version, "SKILL_ALIAS_VERSION_INVALID")
            for alias, version in _object(
                values,
                "SKILL_ALIAS_MAP_INVALID",
            ).items()
        }
        for skill_id, values in _object(
            payload.get("aliases", {}),
            "SKILL_ALIASES_INVALID",
        ).items()
    }
    return SkillReleaseManifest(
        schema=_string(payload.get("schema"), "SKILL_RELEASE_SCHEMA_REQUIRED"),
        revision=int(payload.get("revision", 0)),
        releases=releases,
        aliases=aliases,
    )


def _frontmatter(markdown: str) -> dict[str, str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillDefinitionInvalidError("SKILL.md must start with frontmatter")
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    else:
        raise SkillDefinitionInvalidError("SKILL.md frontmatter is not terminated")
    if not result.get("name") or not result.get("description"):
        raise SkillDefinitionInvalidError(
            "SKILL.md frontmatter requires name and description"
        )
    if len(result["description"]) > 1024:
        raise SkillDefinitionInvalidError(
            "SKILL.md description exceeds Deep Agents limit"
        )
    return result


def _tool(value: Any) -> ToolRequirement:
    if isinstance(value, str):
        return ToolRequirement(value, "1.x")
    raw = _object(value, "SKILL_TOOL_REQUIREMENT_INVALID")
    return ToolRequirement(
        _string(raw.get("name"), "SKILL_TOOL_NAME_REQUIRED"),
        _string(raw.get("version", "1.x"), "SKILL_TOOL_VERSION_REQUIRED"),
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillDefinitionInvalidError(
            f"invalid JSON-compatible YAML: {path}"
        ) from exc


def _object(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SkillDefinitionInvalidError(code)
    return value


def _list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise SkillDefinitionInvalidError(code)
    return value


def _string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise SkillDefinitionInvalidError(code)
    return value


def _strings(value: Any, code: str) -> list[str]:
    rows = _list(value, code)
    if not all(isinstance(item, str) and item for item in rows):
        raise SkillDefinitionInvalidError(code)
    return rows
