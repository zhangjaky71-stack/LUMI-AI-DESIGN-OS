from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .semver import SemVer

_AGENT_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_ALIAS = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


class AgentReleaseStatus(StrEnum):
    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    PRODUCTION = "PRODUCTION"
    DEPRECATED = "DEPRECATED"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class AgentReleaseRecord:
    agent_id: str
    version: str
    status: AgentReleaseStatus
    eval_profile: str
    eval_status: str | None = None
    eval_evidence: str | None = None
    published_at: str | None = None

    def __post_init__(self) -> None:
        if not _AGENT_ID.fullmatch(self.agent_id):
            raise ValueError("AGENT_RELEASE_ID_INVALID")
        SemVer.parse(self.version)
        if not _ALIAS.fullmatch(self.eval_profile):
            raise ValueError("AGENT_RELEASE_EVAL_PROFILE_INVALID")
        if self.status == AgentReleaseStatus.PRODUCTION and self.eval_status != "passed":
            raise ValueError("AGENT_PRODUCTION_REQUIRES_PASSED_EVAL")


@dataclass(frozen=True, slots=True)
class AgentReleaseManifest:
    schema: str
    revision: int
    releases: tuple[AgentReleaseRecord, ...]
    aliases: dict[str, dict[str, str]]

    def __post_init__(self) -> None:
        if self.schema != "lumi.agent-registry.release.v1":
            raise ValueError("AGENT_RELEASE_SCHEMA_UNSUPPORTED")
        if self.revision < 1:
            raise ValueError("AGENT_RELEASE_REVISION_INVALID")
        seen: set[tuple[str, str]] = set()
        for item in self.releases:
            key = (item.agent_id, item.version)
            if key in seen:
                raise ValueError(f"AGENT_RELEASE_DUPLICATE:{item.agent_id}@{item.version}")
            seen.add(key)
        for agent_id, aliases in self.aliases.items():
            if not _AGENT_ID.fullmatch(agent_id):
                raise ValueError("AGENT_ALIAS_ID_INVALID")
            for alias, version in aliases.items():
                if not _ALIAS.fullmatch(alias):
                    raise ValueError("AGENT_ALIAS_NAME_INVALID")
                SemVer.parse(version)
