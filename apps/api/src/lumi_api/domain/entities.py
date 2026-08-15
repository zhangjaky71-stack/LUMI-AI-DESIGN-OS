from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from .errors import InvariantViolation
from .ids import new_uuid7
from .states import (
    AGENT_RUN_TRANSITIONS,
    ARTIFACT_VERSION_TRANSITIONS,
    GENERATION_TRANSITIONS,
    PROJECT_TRANSITIONS,
    TASK_TRANSITIONS,
    AgentRunStatus,
    ArtifactVersionStatus,
    GenerationStatus,
    ProjectStatus,
    TaskStatus,
    require_transition,
)
from .value_objects import (
    Budget,
    MimeType,
    ModelRef,
    Money,
    OperationIdentity,
    ProviderRef,
    RightsPolicy,
    StorageRef,
    Usage,
)


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class CostEntryKind(StrEnum):
    CHARGE = "charge"
    REVERSAL = "reversal"
    ADJUSTMENT = "adjustment"


@dataclass(frozen=True, slots=True)
class Organization:
    name: str
    slug: str
    plan: str = "free"
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    settings: Mapping[str, str] = field(default_factory=dict)
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.slug.strip():
            raise InvariantViolation("organization name/slug are required")
        object.__setattr__(self, "settings", MappingProxyType(dict(self.settings)))


@dataclass(frozen=True, slots=True)
class Workspace:
    organization_id: UUID
    name: str
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvariantViolation("workspace name is required")


@dataclass(frozen=True, slots=True)
class Project:
    organization_id: UUID
    workspace_id: UUID
    name: str
    brief: str = ""
    status: ProjectStatus = ProjectStatus.DRAFT
    active_branch_id: UUID | None = None
    brand_id: UUID | None = None
    settings: Mapping[str, str] = field(default_factory=dict)
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvariantViolation("project name is required")
        object.__setattr__(self, "settings", MappingProxyType(dict(self.settings)))

    def transition(self, target: ProjectStatus) -> Project:
        require_transition(self.status, target, PROJECT_TRANSITIONS)
        return replace(self, status=target)


@dataclass(frozen=True, slots=True)
class Brand:
    organization_id: UUID
    name: str
    profile: Mapping[str, str] = field(default_factory=dict)
    rules: tuple[str, ...] = ()
    forbidden_rules: tuple[str, ...] = ()
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvariantViolation("brand name is required")
        object.__setattr__(self, "profile", MappingProxyType(dict(self.profile)))


@dataclass(frozen=True, slots=True)
class Asset:
    organization_id: UUID
    storage: StorageRef
    mime_type: MimeType
    source: str
    rights: RightsPolicy
    semantic_metadata: Mapping[str, str] = field(default_factory=dict)
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if self.storage.owner_organization_id != self.organization_id:
            raise InvariantViolation("asset storage ownership must match organization")
        if not self.source.strip():
            raise InvariantViolation("asset source is required")
        object.__setattr__(
            self,
            "semantic_metadata",
            MappingProxyType(dict(self.semantic_metadata)),
        )


@dataclass(frozen=True, slots=True)
class DesignDocument:
    organization_id: UUID
    project_id: UUID
    name: str
    ir_version: str
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.ir_version.strip():
            raise InvariantViolation("design document name/ir_version are required")


@dataclass(frozen=True, slots=True)
class Branch:
    organization_id: UUID
    project_id: UUID
    name: str
    head_version_id: UUID | None = None
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvariantViolation("branch name is required")


@dataclass(frozen=True, slots=True)
class Artifact:
    organization_id: UUID
    project_id: UUID
    kind: str
    design_document_id: UUID | None = None
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise InvariantViolation("artifact kind is required")


@dataclass(frozen=True, slots=True)
class ArtifactVersion:
    organization_id: UUID
    artifact_id: UUID
    branch_id: UUID
    ordinal: int
    status: ArtifactVersionStatus = ArtifactVersionStatus.DRAFT
    parent_version_ids: tuple[UUID, ...] = ()
    payload_ref: str | None = None
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise InvariantViolation("artifact version ordinal must be >= 1")
        if self.id in self.parent_version_ids:
            raise InvariantViolation("artifact version cannot parent itself")

    def transition(self, target: ArtifactVersionStatus) -> ArtifactVersion:
        require_transition(self.status, target, ARTIFACT_VERSION_TRANSITIONS)
        return replace(self, status=target)


@dataclass(frozen=True, slots=True)
class AgentRun:
    organization_id: UUID
    project_id: UUID
    thread_id: str
    graph_version: str
    agent_config_version: str
    budget: Budget
    status: AgentRunStatus = AgentRunStatus.PENDING
    usage: Usage = Usage()
    trace_refs: tuple[str, ...] = ()
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if not self.thread_id.strip() or not self.graph_version.strip():
            raise InvariantViolation("thread_id/graph_version are required")
        if not self.agent_config_version.strip():
            raise InvariantViolation("agent_config_version is required")

    def transition(self, target: AgentRunStatus) -> AgentRun:
        require_transition(self.status, target, AGENT_RUN_TRANSITIONS)
        return replace(self, status=target)


@dataclass(frozen=True, slots=True)
class Task:
    organization_id: UUID
    project_id: UUID
    name: str
    dependency_ids: tuple[UUID, ...] = ()
    status: TaskStatus = TaskStatus.PENDING
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvariantViolation("task name is required")
        if self.id in self.dependency_ids:
            raise InvariantViolation("task cannot depend on itself")
        if len(self.dependency_ids) != len(set(self.dependency_ids)):
            raise InvariantViolation("task dependencies must be unique")

    def transition(self, target: TaskStatus) -> Task:
        require_transition(self.status, target, TASK_TRANSITIONS)
        return replace(self, status=target)


@dataclass(frozen=True, slots=True)
class Generation:
    organization_id: UUID
    project_id: UUID
    operation: OperationIdentity
    model: ModelRef
    provider_request: ProviderRef | None = None
    agent_run_id: UUID | None = None
    status: GenerationStatus = GenerationStatus.PENDING
    id: UUID = field(default_factory=new_uuid7)

    def transition(self, target: GenerationStatus) -> Generation:
        require_transition(self.status, target, GENERATION_TRANSITIONS)
        return replace(self, status=target)


@dataclass(frozen=True, slots=True)
class CostEntry:
    organization_id: UUID
    amount: Money
    operation_id: UUID
    kind: CostEntryKind = CostEntryKind.CHARGE
    related_entry_id: UUID | None = None
    description: str = ""
    id: UUID = field(default_factory=new_uuid7)

    def __post_init__(self) -> None:
        if self.kind in {CostEntryKind.REVERSAL, CostEntryKind.ADJUSTMENT}:
            if self.related_entry_id is None:
                raise InvariantViolation("reversal/adjustment must reference an existing entry")
        elif self.related_entry_id is not None:
            raise InvariantViolation("charge cannot reference related_entry_id")
