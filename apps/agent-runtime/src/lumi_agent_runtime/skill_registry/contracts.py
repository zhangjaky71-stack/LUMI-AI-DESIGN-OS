from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from lumi_agent_runtime.agent_registry.requirements import SkillRequirement, ToolRequirement
from lumi_agent_runtime.agent_registry.semver import SemVer

_SKILL_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class SkillReleaseStatus(StrEnum):
    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    PRODUCTION = "PRODUCTION"
    DEPRECATED = "DEPRECATED"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    skill_id: str
    version: str
    summary: str
    compatible_agents: tuple[str, ...]
    required_tools: tuple[ToolRequirement, ...]
    required_capabilities: tuple[str, ...]
    input_schema: str
    output_schema: str
    permissions: tuple[str, ...]
    dependencies: tuple[SkillRequirement, ...]
    eval_profile: str
    task_types: tuple[str, ...]
    skill_markdown: str
    resources: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _SKILL_ID.fullmatch(self.skill_id):
            raise ValueError(f"SKILL_ID_INVALID:{self.skill_id}")
        SemVer.parse(self.version)
        if not self.summary or len(self.summary) > 1024:
            raise ValueError("SKILL_SUMMARY_INVALID")
        if not self.compatible_agents or len(set(self.compatible_agents)) != len(self.compatible_agents):
            raise ValueError("SKILL_COMPATIBLE_AGENTS_INVALID")
        if not all(_SKILL_ID.fullmatch(item) for item in self.compatible_agents):
            raise ValueError("SKILL_COMPATIBLE_AGENT_INVALID")
        if not self.input_schema or not self.output_schema:
            raise ValueError("SKILL_SCHEMA_REFERENCE_REQUIRED")
        if not _NAME.fullmatch(self.eval_profile):
            raise ValueError("SKILL_EVAL_PROFILE_INVALID")
        if len(set(self.permissions)) != len(self.permissions):
            raise ValueError("SKILL_PERMISSION_DUPLICATE")
        if not all(_NAME.fullmatch(item) for item in self.permissions):
            raise ValueError("SKILL_PERMISSION_INVALID")
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("SKILL_CAPABILITY_DUPLICATE")
        if not all(_NAME.fullmatch(item) for item in self.required_capabilities):
            raise ValueError("SKILL_CAPABILITY_INVALID")
        if len(set(self.task_types)) != len(self.task_types):
            raise ValueError("SKILL_TASK_TYPE_DUPLICATE")
        if not self.skill_markdown or len(self.skill_markdown.encode("utf-8")) > 10 * 1024 * 1024:
            raise ValueError("SKILL_MARKDOWN_SIZE_INVALID")
        if len(self.resources) > 128:
            raise ValueError("SKILL_RESOURCE_COUNT_INVALID")
        total = len(self.skill_markdown.encode("utf-8"))
        for path, value in self.resources.items():
            if not _safe_resource_path(path):
                raise ValueError(f"SKILL_RESOURCE_PATH_INVALID:{path}")
            total += len(value.encode("utf-8"))
        if total > 16 * 1024 * 1024:
            raise ValueError("SKILL_RESOURCE_BUDGET_EXCEEDED")
        _json_guard(self.metadata, depth=0)

    @property
    def identity(self) -> str:
        return f"{self.skill_id}@{self.version}"

    @property
    def markdown_hash(self) -> str:
        return hashlib.sha256(self.skill_markdown.encode("utf-8")).hexdigest()

    @property
    def content_hash(self) -> str:
        resources = {
            path: hashlib.sha256(value.encode("utf-8")).hexdigest()
            for path, value in sorted(self.resources.items())
        }
        payload = {
            "id": self.skill_id,
            "version": self.version,
            "summary": self.summary,
            "compatible_agents": list(self.compatible_agents),
            "required_tools": [
                {"name": item.name, "version": item.version_constraint}
                for item in self.required_tools
            ],
            "required_capabilities": list(self.required_capabilities),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "permissions": list(self.permissions),
            "dependencies": [item.ref for item in self.dependencies],
            "eval_profile": self.eval_profile,
            "task_types": list(self.task_types),
            "markdown_hash": self.markdown_hash,
            "resources": resources,
            "metadata": self.metadata,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SkillReleaseRecord:
    skill_id: str
    version: str
    status: SkillReleaseStatus
    eval_profile: str
    eval_status: str | None = None
    eval_evidence: str | None = None

    def __post_init__(self) -> None:
        SemVer.parse(self.version)
        if self.status == SkillReleaseStatus.PRODUCTION and self.eval_status != "passed":
            raise ValueError("SKILL_PRODUCTION_REQUIRES_PASSED_EVAL")


@dataclass(frozen=True, slots=True)
class SkillReleaseManifest:
    schema: str
    revision: int
    releases: tuple[SkillReleaseRecord, ...]
    aliases: dict[str, dict[str, str]]


@dataclass(frozen=True, slots=True)
class SkillExecutionContext:
    agent_id: str
    allowed_tools: frozenset[str]
    granted_permissions: frozenset[str]
    available_capabilities: frozenset[str]


@dataclass(frozen=True, slots=True)
class ResolvedSkill:
    definition: SkillDefinition
    release_status: SkillReleaseStatus
    requested_ref: str


@dataclass(frozen=True, slots=True)
class ResolvedSkillPack:
    roots: tuple[str, ...]
    skills: tuple[ResolvedSkill, ...]
    manifest_revision: int

    @property
    def freeze_hash(self) -> str:
        payload = {
            "roots": list(self.roots),
            "manifest_revision": self.manifest_revision,
            "skills": [
                {
                    "id": item.definition.skill_id,
                    "version": item.definition.version,
                    "hash": item.definition.content_hash,
                    "status": item.release_status.value,
                }
                for item in self.skills
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def _safe_resource_path(path: str) -> bool:
    if not path or path.startswith(("/", "\\")) or "\\" in path:
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _json_guard(value: Any, *, depth: int) -> None:
    if depth > 16:
        raise ValueError("SKILL_METADATA_TOO_DEEP")
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("SKILL_METADATA_NONFINITE")
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("SKILL_METADATA_NON_STRING_KEY")
        for child in value.values():
            _json_guard(child, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _json_guard(child, depth=depth + 1)
        return
    raise ValueError("SKILL_METADATA_UNSUPPORTED")
