from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from lumi_agent_runtime.agent_registry.definition import AgentDefinition
from lumi_agent_runtime.agent_registry.loader import AgentDefinitionLoader

from .contracts import AgentArchetype, AgentTeamProfile, team_profile
from .delegation import validate_team_delegation_graph

CANONICAL_AGENT_IDS = (
    "creative-director",
    "brand-strategist",
    "research-agent",
    "prompt-engineer",
    "image-generator",
    "image-editor",
    "workflow-engineer",
    "critic-agent",
    "logo-designer",
    "web-designer",
    "ui-designer",
    "video-generator",
    "video-editor",
    "social-media-designer",
    "presentation-designer",
    "data-visualization-agent",
)
P0_AGENT_IDS = CANONICAL_AGENT_IDS[:8]
P1_AGENT_IDS = CANONICAL_AGENT_IDS[8:]


@dataclass(frozen=True, slots=True)
class AgentTeamMember:
    agent_id: str
    version: str
    tier: str

    def __post_init__(self) -> None:
        if not self.agent_id or not self.version or self.tier not in {"P0", "P1"}:
            raise ValueError("AGENT_TEAM_MEMBER_INVALID")

    @property
    def ref(self) -> str:
        return f"{self.agent_id}@{self.version}"


@dataclass(frozen=True, slots=True)
class AgentTeamManifest:
    team_id: str
    version: str
    root_agent: str
    members: tuple[AgentTeamMember, ...]
    image_flow: tuple[str, ...]
    schema: str = "lumi.agent-team.v1"

    def __post_init__(self) -> None:
        if self.schema != "lumi.agent-team.v1":
            raise ValueError("AGENT_TEAM_MANIFEST_SCHEMA_INVALID")
        if not self.team_id or not self.version:
            raise ValueError("AGENT_TEAM_MANIFEST_IDENTITY_INVALID")
        ids = tuple(item.agent_id for item in self.members)
        if ids != CANONICAL_AGENT_IDS:
            raise ValueError("AGENT_TEAM_CANONICAL_MEMBER_SET_INVALID")
        if tuple(item.tier for item in self.members[:8]) != ("P0",) * 8:
            raise ValueError("AGENT_TEAM_P0_TIER_INVALID")
        if tuple(item.tier for item in self.members[8:]) != ("P1",) * 8:
            raise ValueError("AGENT_TEAM_P1_TIER_INVALID")
        if self.root_agent != "creative-director":
            raise ValueError("AGENT_TEAM_ROOT_INVALID")
        if len(self.image_flow) < 4:
            raise ValueError("AGENT_TEAM_IMAGE_FLOW_TOO_SHORT")
        if any(agent_id not in ids for agent_id in self.image_flow):
            raise ValueError("AGENT_TEAM_IMAGE_FLOW_UNKNOWN_AGENT")

    @property
    def content_hash(self) -> str:
        payload = {
            "schema": self.schema,
            "team_id": self.team_id,
            "version": self.version,
            "root_agent": self.root_agent,
            "members": [
                {
                    "agent_id": item.agent_id,
                    "version": item.version,
                    "tier": item.tier,
                }
                for item in self.members
            ],
            "image_flow": list(self.image_flow),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class CompiledAgentTeam:
    manifest: AgentTeamManifest
    definitions: Mapping[str, AgentDefinition]
    profiles: Mapping[str, AgentTeamProfile]

    def resolve(self, agent_id: str) -> AgentDefinition:
        try:
            return self.definitions[agent_id]
        except KeyError as exc:
            raise KeyError(f"AGENT_TEAM_UNKNOWN_AGENT:{agent_id}") from exc


def load_team_manifest(path: Path) -> AgentTeamManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("AGENT_TEAM_MANIFEST_NOT_OBJECT")
    allowed = {
        "schema",
        "team_id",
        "version",
        "root_agent",
        "members",
        "image_flow",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError("AGENT_TEAM_MANIFEST_UNKNOWN_FIELDS:" + ",".join(sorted(unknown)))
    members_raw = payload.get("members")
    if not isinstance(members_raw, list):
        raise ValueError("AGENT_TEAM_MEMBERS_NOT_LIST")
    members = tuple(
        AgentTeamMember(
            agent_id=_required_text(item, "agent_id"),
            version=_required_text(item, "version"),
            tier=_required_text(item, "tier"),
        )
        for item in members_raw
        if isinstance(item, dict)
    )
    if len(members) != len(members_raw):
        raise ValueError("AGENT_TEAM_MEMBER_NOT_OBJECT")
    image_flow = payload.get("image_flow")
    if not isinstance(image_flow, list):
        raise ValueError("AGENT_TEAM_IMAGE_FLOW_NOT_LIST")
    return AgentTeamManifest(
        schema=str(payload.get("schema", "")),
        team_id=_required_text(payload, "team_id"),
        version=_required_text(payload, "version"),
        root_agent=_required_text(payload, "root_agent"),
        members=members,
        image_flow=tuple(str(item) for item in image_flow),
    )


def compile_agent_team(
    *,
    repo_root: Path,
    manifest_path: Path | None = None,
) -> CompiledAgentTeam:
    manifest = load_team_manifest(
        manifest_path or repo_root / "config/agent-team/team.v1.json"
    )
    loader = AgentDefinitionLoader(repo_root / "agents")
    definitions: dict[str, AgentDefinition] = {}
    profiles: dict[str, AgentTeamProfile] = {}
    for member in manifest.members:
        loaded = loader.load(member.agent_id, member.version)
        if loaded.definition.agent_id != member.agent_id:
            raise ValueError("AGENT_TEAM_DEFINITION_ID_MISMATCH")
        definitions[member.agent_id] = loaded.definition
        profiles[member.agent_id] = team_profile(loaded.definition)

    validate_team_delegation_graph(definitions)
    _validate_role_invariants(definitions, profiles)
    return CompiledAgentTeam(
        manifest=manifest,
        definitions=MappingProxyType(definitions),
        profiles=MappingProxyType(profiles),
    )


def _validate_role_invariants(
    definitions: Mapping[str, AgentDefinition],
    profiles: Mapping[str, AgentTeamProfile],
) -> None:
    critic = definitions["critic-agent"]
    if profiles["critic-agent"].archetype != AgentArchetype.CRITIC:
        raise ValueError("AGENT_TEAM_CRITIC_ARCHETYPE_INVALID")
    write_tools = {
        "asset.write-derived",
        "sandbox.execute",
    }
    if write_tools & set(critic.allowed_tools):
        raise ValueError("AGENT_TEAM_CRITIC_WRITE_TOOL_FORBIDDEN")
    if any("write" in permission for permission in critic.permissions):
        raise ValueError("AGENT_TEAM_CRITIC_WRITE_PERMISSION_FORBIDDEN")

    brand = profiles["brand-strategist"]
    if "brand-rule.write" not in brand.approval_gated_actions:
        raise ValueError("AGENT_TEAM_BRAND_WRITE_APPROVAL_GATE_REQUIRED")
    if profiles["video-generator"].supports_waiting_external is not True:
        raise ValueError("AGENT_TEAM_VIDEO_GENERATOR_WAITING_EXTERNAL_REQUIRED")
    if profiles["video-editor"].supports_waiting_external is not True:
        raise ValueError("AGENT_TEAM_VIDEO_EDITOR_WAITING_EXTERNAL_REQUIRED")

    root = profiles["creative-director"]
    required_root_delegates = set(CANONICAL_AGENT_IDS) - {"creative-director"}
    if set(root.delegation_allowlist) != required_root_delegates:
        raise ValueError("AGENT_TEAM_ROOT_DELEGATION_ALLOWLIST_INVALID")


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AGENT_TEAM_MANIFEST_FIELD_INVALID:{key}")
    return value
