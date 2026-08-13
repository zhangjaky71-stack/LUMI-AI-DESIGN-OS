from __future__ import annotations

import re
from dataclasses import dataclass

_AGENT_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,255}$")
_MEMORY_SCOPES = {"project", "brand", "organization", "user", "session"}


@dataclass(frozen=True, slots=True)
class ToolRequirement:
    name: str
    version_constraint: str = "1.x"

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.name):
            raise ValueError(f"AGENT_TOOL_NAME_INVALID:{self.name}")
        if not self.version_constraint or len(self.version_constraint) > 64:
            raise ValueError("AGENT_TOOL_VERSION_CONSTRAINT_INVALID")


@dataclass(frozen=True, slots=True)
class SkillRequirement:
    skill_id: str
    version_constraint: str

    def __post_init__(self) -> None:
        if not _AGENT_ID.fullmatch(self.skill_id):
            raise ValueError(f"AGENT_SKILL_ID_INVALID:{self.skill_id}")
        if not self.version_constraint or len(self.version_constraint) > 64:
            raise ValueError("AGENT_SKILL_VERSION_CONSTRAINT_INVALID")

    @property
    def ref(self) -> str:
        return f"{self.skill_id}@{self.version_constraint}"

    @classmethod
    def parse(cls, value: str) -> "SkillRequirement":
        if "@" not in value:
            raise ValueError(f"AGENT_SKILL_REF_INVALID:{value}")
        skill_id, selector = value.rsplit("@", 1)
        return cls(skill_id=skill_id, version_constraint=selector)


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not set(self.read) <= _MEMORY_SCOPES or not set(self.write) <= _MEMORY_SCOPES:
            raise ValueError("AGENT_MEMORY_SCOPE_INVALID")
        if len(set(self.read)) != len(self.read) or len(set(self.write)) != len(self.write):
            raise ValueError("AGENT_MEMORY_SCOPE_DUPLICATE")
