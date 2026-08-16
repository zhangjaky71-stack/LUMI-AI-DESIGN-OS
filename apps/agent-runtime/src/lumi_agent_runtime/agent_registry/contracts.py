from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from lumi_agent_runtime.deep_runtime.contracts import (
    DelegationLimits,
    PermissionScope,
    ResolvedAgentConfig,
)

_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_ALIAS = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_SKILL_REF = re.compile(
    r"^[a-z][a-z0-9_-]{0,62}@[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$"
)


@dataclass(frozen=True, slots=True)
class AgentScope:
    organization_id: UUID | None = None
    project_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.project_id is not None and self.organization_id is None:
            raise ValueError("AGENT_REGISTRY_PROJECT_SCOPE_REQUIRES_ORG")

    @classmethod
    def global_scope(cls) -> "AgentScope":
        return cls()

    @classmethod
    def organization(cls, organization_id: UUID) -> "AgentScope":
        return cls(organization_id=organization_id)

    @classmethod
    def project(
        cls,
        organization_id: UUID,
        project_id: UUID,
    ) -> "AgentScope":
        return cls(
            organization_id=organization_id,
            project_id=project_id,
        )

    @property
    def kind(self) -> str:
        if self.project_id is not None:
            return "project"
        if self.organization_id is not None:
            return "organization"
        return "global"

    @property
    def key(self) -> str:
        if self.project_id is not None:
            return f"project:{self.organization_id}:{self.project_id}"
        if self.organization_id is not None:
            return f"organization:{self.organization_id}"
        return "global"

    def visible_chain(self) -> tuple["AgentScope", ...]:
        if self.project_id is not None:
            return (
                self,
                AgentScope.organization(self.organization_id),
                AgentScope.global_scope(),
            )
        if self.organization_id is not None:
            return (self, AgentScope.global_scope())
        return (self,)


@dataclass(frozen=True, slots=True)
class AgentManifest:
    agent_id: str
    version: str
    role: str
    description: str
    system_prompt: str
    model_profile: str
    allowed_tools: tuple[str, ...]
    skill_refs: tuple[str, ...]
    context_policy: str
    memory_read_scopes: tuple[str, ...] = ()
    memory_write_scopes: tuple[str, ...] = ()
    sandbox_execute: bool = False
    subagent_refs: tuple[str, ...] = ()
    output_schema: str = "AgentTaskResult"
    max_steps: int = 64
    delegation: DelegationLimits = field(default_factory=DelegationLimits)

    def __post_init__(self) -> None:
        validate_agent_id(self.agent_id)
        validate_version(self.version)
        if not self.description or len(self.description) > 2_000:
            raise ValueError("AGENT_REGISTRY_DESCRIPTION_INVALID")
        if len(self.subagent_refs) > self.delegation.max_children_per_agent:
            raise ValueError("AGENT_REGISTRY_CHILD_LIMIT_EXCEEDED")
        child_ids: list[str] = []
        for ref in self.subagent_refs:
            child_id, _ = parse_agent_ref(ref)
            child_ids.append(child_id)
        if len(child_ids) != len(set(child_ids)):
            raise ValueError("AGENT_REGISTRY_SUBAGENT_DUPLICATE")
        for ref in self.skill_refs:
            if not _SKILL_REF.fullmatch(ref):
                raise ValueError(f"AGENT_REGISTRY_SKILL_REF_INVALID:{ref}")
        if len(self.skill_refs) != len(set(self.skill_refs)):
            raise ValueError("AGENT_REGISTRY_SKILL_REF_DUPLICATE")
        PermissionScope(
            allowed_tools=self.allowed_tools,
            sandbox_execute=self.sandbox_execute,
            memory_read_scopes=self.memory_read_scopes,
            memory_write_scopes=self.memory_write_scopes,
            allowed_subagents=tuple(child_ids),
        )
        ResolvedAgentConfig(
            agent_id=self.agent_id,
            exact_version=self.version,
            role=self.role,
            system_prompt=self.system_prompt,
            model_profile=self.model_profile,
            allowed_tools=self.allowed_tools,
            skill_refs=self.skill_refs,
            context_policy=self.context_policy,
            memory_read_scopes=self.memory_read_scopes,
            memory_write_scopes=self.memory_write_scopes,
            sandbox_execute=self.sandbox_execute,
            subagents=(),
            output_schema=self.output_schema,
            max_steps=self.max_steps,
            delegation=self.delegation,
        )

    def with_pinned_subagents(
        self,
        refs: tuple[str, ...],
    ) -> "AgentManifest":
        return replace(self, subagent_refs=refs)


@dataclass(frozen=True, slots=True)
class PublishedAgent:
    scope: AgentScope
    manifest: AgentManifest
    content_hash: str
    provenance_ref: str
    published_by: str
    published_at: str

    @property
    def identity(self) -> str:
        return f"{self.manifest.agent_id}@{self.manifest.version}"


@dataclass(frozen=True, slots=True)
class AgentAlias:
    scope: AgentScope
    agent_id: str
    alias: str
    exact_version: str
    history: tuple[str, ...]
    revision: int
    updated_by: str
    updated_at: str

    def __post_init__(self) -> None:
        validate_agent_id(self.agent_id)
        validate_alias(self.alias)
        validate_version(self.exact_version)
        if self.revision < 1:
            raise ValueError("AGENT_REGISTRY_ALIAS_REVISION_INVALID")
        for version in self.history:
            if not _VERSION.fullmatch(version):
                raise ValueError("AGENT_REGISTRY_ALIAS_HISTORY_INVALID")


def validate_agent_id(value: str) -> None:
    if not _NAME.fullmatch(value):
        raise ValueError("AGENT_REGISTRY_AGENT_ID_INVALID")


def validate_version(value: str) -> None:
    if not _VERSION.fullmatch(value):
        raise ValueError("AGENT_REGISTRY_VERSION_INVALID")


def validate_alias(value: str) -> None:
    if not _ALIAS.fullmatch(value):
        raise ValueError("AGENT_REGISTRY_ALIAS_INVALID")


def parse_agent_ref(value: str) -> tuple[str, str]:
    if value.count("@") != 1:
        raise ValueError("AGENT_REGISTRY_REF_INVALID")
    agent_id, selector = value.split("@", 1)
    try:
        validate_agent_id(agent_id)
        validate_version(selector)
    except ValueError as exc:
        raise ValueError("AGENT_REGISTRY_REF_INVALID") from exc
    return agent_id, selector


def scope_to_dict(scope: AgentScope) -> dict[str, str | None]:
    return {
        "organization_id": (
            str(scope.organization_id) if scope.organization_id else None
        ),
        "project_id": str(scope.project_id) if scope.project_id else None,
    }


def scope_from_dict(value: dict[str, Any]) -> AgentScope:
    organization = value.get("organization_id")
    project = value.get("project_id")
    return AgentScope(
        organization_id=UUID(organization) if organization else None,
        project_id=UUID(project) if project else None,
    )


def manifest_to_dict(manifest: AgentManifest) -> dict[str, Any]:
    return {
        "agent_id": manifest.agent_id,
        "version": manifest.version,
        "role": manifest.role,
        "description": manifest.description,
        "system_prompt": manifest.system_prompt,
        "model_profile": manifest.model_profile,
        "allowed_tools": list(manifest.allowed_tools),
        "skill_refs": list(manifest.skill_refs),
        "context_policy": manifest.context_policy,
        "memory_read_scopes": list(manifest.memory_read_scopes),
        "memory_write_scopes": list(manifest.memory_write_scopes),
        "sandbox_execute": manifest.sandbox_execute,
        "subagent_refs": list(manifest.subagent_refs),
        "output_schema": manifest.output_schema,
        "max_steps": manifest.max_steps,
        "delegation": {
            "max_depth": manifest.delegation.max_depth,
            "max_total_subagent_calls": (
                manifest.delegation.max_total_subagent_calls
            ),
            "max_parallel_subagents": (
                manifest.delegation.max_parallel_subagents
            ),
            "max_children_per_agent": (
                manifest.delegation.max_children_per_agent
            ),
        },
    }


def manifest_from_dict(value: dict[str, Any]) -> AgentManifest:
    delegation = value.get("delegation", {})
    return AgentManifest(
        agent_id=value["agent_id"],
        version=value["version"],
        role=value["role"],
        description=value["description"],
        system_prompt=value["system_prompt"],
        model_profile=value["model_profile"],
        allowed_tools=tuple(value.get("allowed_tools", ())),
        skill_refs=tuple(value.get("skill_refs", ())),
        context_policy=value["context_policy"],
        memory_read_scopes=tuple(value.get("memory_read_scopes", ())),
        memory_write_scopes=tuple(value.get("memory_write_scopes", ())),
        sandbox_execute=bool(value.get("sandbox_execute", False)),
        subagent_refs=tuple(value.get("subagent_refs", ())),
        output_schema=value.get("output_schema", "AgentTaskResult"),
        max_steps=int(value.get("max_steps", 64)),
        delegation=DelegationLimits(
            max_depth=int(delegation.get("max_depth", 1)),
            max_total_subagent_calls=int(
                delegation.get("max_total_subagent_calls", 12)
            ),
            max_parallel_subagents=int(
                delegation.get("max_parallel_subagents", 3)
            ),
            max_children_per_agent=int(
                delegation.get("max_children_per_agent", 6)
            ),
        ),
    )


def published_to_dict(release: PublishedAgent) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "scope": scope_to_dict(release.scope),
        "manifest": manifest_to_dict(release.manifest),
        "content_hash": release.content_hash,
        "provenance_ref": release.provenance_ref,
        "published_by": release.published_by,
        "published_at": release.published_at,
    }


def published_from_dict(value: dict[str, Any]) -> PublishedAgent:
    return PublishedAgent(
        scope=scope_from_dict(value["scope"]),
        manifest=manifest_from_dict(value["manifest"]),
        content_hash=value["content_hash"],
        provenance_ref=value["provenance_ref"],
        published_by=value["published_by"],
        published_at=value["published_at"],
    )


def alias_to_dict(alias: AgentAlias) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "scope": scope_to_dict(alias.scope),
        "agent_id": alias.agent_id,
        "alias": alias.alias,
        "exact_version": alias.exact_version,
        "history": list(alias.history),
        "revision": alias.revision,
        "updated_by": alias.updated_by,
        "updated_at": alias.updated_at,
    }


def alias_from_dict(value: dict[str, Any]) -> AgentAlias:
    return AgentAlias(
        scope=scope_from_dict(value["scope"]),
        agent_id=value["agent_id"],
        alias=value["alias"],
        exact_version=value["exact_version"],
        history=tuple(value.get("history", ())),
        revision=int(value["revision"]),
        updated_by=value["updated_by"],
        updated_at=value["updated_at"],
    )
