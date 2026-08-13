from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .requirements import MemoryPolicy, SkillRequirement, ToolRequirement
from .semver import SemVer

_AGENT_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_POLICY_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SCHEMA_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    agent_id: str
    version: str
    role: str
    description: str
    model_policy: str
    tools: tuple[ToolRequirement, ...]
    skills: tuple[SkillRequirement, ...]
    context_policy: str
    memory_policy: MemoryPolicy
    budget_policy: str
    permissions: dict[str, bool]
    output_schema: str
    eval_profile: str
    system_prompt: str
    max_steps: int = 64
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _AGENT_ID.fullmatch(self.agent_id):
            raise ValueError(f"AGENT_ID_INVALID:{self.agent_id}")
        SemVer.parse(self.version)
        if not self.role or len(self.role) > 128:
            raise ValueError("AGENT_ROLE_INVALID")
        if not self.description or len(self.description) > 2000:
            raise ValueError("AGENT_DESCRIPTION_INVALID")
        for value, code in (
            (self.model_policy, "AGENT_MODEL_POLICY_INVALID"),
            (self.context_policy, "AGENT_CONTEXT_POLICY_INVALID"),
            (self.budget_policy, "AGENT_BUDGET_POLICY_INVALID"),
            (self.eval_profile, "AGENT_EVAL_PROFILE_INVALID"),
        ):
            if not _POLICY_ID.fullmatch(value):
                raise ValueError(code)
        if not _SCHEMA_ID.fullmatch(self.output_schema):
            raise ValueError("AGENT_OUTPUT_SCHEMA_INVALID")
        if not self.system_prompt or len(self.system_prompt) > 65536:
            raise ValueError("AGENT_SYSTEM_PROMPT_INVALID")
        if not 1 <= self.max_steps <= 256:
            raise ValueError("AGENT_MAX_STEPS_INVALID")
        tool_names = [item.name for item in self.tools]
        if len(set(tool_names)) != len(tool_names):
            raise ValueError("AGENT_TOOL_DUPLICATE")
        skill_ids = [item.skill_id for item in self.skills]
        if len(set(skill_ids)) != len(skill_ids):
            raise ValueError("AGENT_SKILL_DUPLICATE")
        if any(not _POLICY_ID.fullmatch(key) for key in self.permissions):
            raise ValueError("AGENT_PERMISSION_KEY_INVALID")
        if "sandbox.execute" in tool_names and not self.permissions.get("sandbox_execute", False):
            raise ValueError("AGENT_SANDBOX_TOOL_REQUIRES_PERMISSION")
        _json_guard(self.metadata, path="$.metadata", depth=0)

    @property
    def identity(self) -> str:
        return f"{self.agent_id}@{self.version}"

    @property
    def system_prompt_hash(self) -> str:
        return hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest()

    @property
    def content_hash(self) -> str:
        payload = {
            "id": self.agent_id,
            "version": self.version,
            "role": self.role,
            "description": self.description,
            "model_policy": self.model_policy,
            "tools": [{"name": item.name, "version": item.version_constraint} for item in self.tools],
            "skills": [item.ref for item in self.skills],
            "context_policy": self.context_policy,
            "memory_policy": {"read": list(self.memory_policy.read), "write": list(self.memory_policy.write)},
            "budget_policy": self.budget_policy,
            "permissions": self.permissions,
            "output_schema": self.output_schema,
            "eval_profile": self.eval_profile,
            "system_prompt_hash": self.system_prompt_hash,
            "max_steps": self.max_steps,
            "metadata": self.metadata,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _json_guard(value: Any, *, path: str, depth: int) -> None:
    if depth > 20:
        raise ValueError("AGENT_METADATA_TOO_DEEP")
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError(f"AGENT_NONFINITE:{path}")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"AGENT_METADATA_NON_STRING_KEY:{path}")
            _json_guard(child, path=f"{path}.{key}", depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _json_guard(child, path=f"{path}[{index}]", depth=depth + 1)
        return
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"AGENT_METADATA_BINARY_FORBIDDEN:{path}")
    raise ValueError(f"AGENT_METADATA_UNSUPPORTED:{path}:{type(value).__name__}")
