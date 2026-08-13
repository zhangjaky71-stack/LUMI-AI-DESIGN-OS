from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType

from .errors import InvariantViolation
from .ids import DomainId, new_uuid7
from .states import (
    AgentRunStatus,
    ArtifactVersionStatus,
    ProjectStatus,
    TaskStatus,
    transition_agent_run,
    transition_artifact_version,
    transition_project,
    transition_task,
)
from .value_objects import Budget, Money, OperationIdentity, ProviderRef, RightsPolicy, StorageRef


@dataclass(slots=True)
class Organization:
    name: str
    slug: str
    id: DomainId = field(default_factory=new_uuid7)
    status: str = "active"
    plan: str = "free"
    settings: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class Workspace:
    organization_id: DomainId
    name: str
    id: DomainId = field(default_factory=new_uuid7)


@dataclass(slots=True)
class Project:
    organization_id: DomainId
    workspace_id: DomainId
    name: str
    id: DomainId = field(default_factory=new_uuid7)
    status: ProjectStatus = ProjectStatus.DRAFT
    brief: Mapping[str, object] = field(default_factory=dict)
    brand_id: DomainId | None = None
    active_branch_id: DomainId | None = None
    settings: Mapping[str, object] = field(default_factory=dict)

    def transition_to(self, target: ProjectStatus) -> None:
        self.status = transition_project(self.status, target)


@dataclass(slots=True)
class Brand:
    organization_id: DomainId
    name: str
    id: DomainId = field(default_factory=new_uuid7)
    profile: Mapping[str, object] = field(default_factory=dict)
    palettes: tuple[str, ...] = ()
    typography: tuple[str, ...] = ()
    logo_asset_ids: tuple[DomainId, ...] = ()
    tone: tuple[str, ...] = ()
    visual_rules: tuple[str, ...] = ()
    forbidden_rules: tuple[str, ...] = ()


@dataclass(slots=True)
class Asset:
    organization_id: DomainId
    storage: StorageRef
    rights: RightsPolicy
    id: DomainId = field(default_factory=new_uuid7)
    source: str = "upload"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.storage.owner_organization_id != self.organization_id:
            raise InvariantViolation("asset storage owner must match asset organization")


@dataclass(slots=True)
class DesignDocument:
    organization_id: DomainId
    project_id: DomainId
    title: str
    id: DomainId = field(default_factory=new_uuid7)
    design_ir_version: str = "1"


@dataclass(slots=True)
class Artifact:
    organization_id: DomainId
    project_id: DomainId
    kind: str
    id: DomainId = field(default_factory=new_uuid7)
    source_asset_ids: tuple[DomainId, ...] = ()


@dataclass(slots=True)
class ArtifactVersion:
    organization_id: DomainId
    artifact_id: DomainId
    content_hash: str
    id: DomainId = field(default_factory=new_uuid7)
    parent_version_id: DomainId | None = None
    status: ArtifactVersionStatus = ArtifactVersionStatus.DRAFT

    def __post_init__(self) -> None:
        if not self.content_hash.strip():
            raise ValueError("content_hash is required")

    def transition_to(self, target: ArtifactVersionStatus) -> None:
        self.status = transition_artifact_version(self.status, target)

    def revised(self, *, content_hash: str) -> ArtifactVersion:
        if self.status is ArtifactVersionStatus.APPROVED:
            raise InvariantViolation("approved artifact versions are immutable; create from a branch")
        return ArtifactVersion(
            organization_id=self.organization_id,
            artifact_id=self.artifact_id,
            content_hash=content_hash,
            parent_version_id=self.id,
        )


@dataclass(slots=True)
class ArtifactBranch:
    organization_id: DomainId
    project_id: DomainId
    artifact_id: DomainId
    name: str
    id: DomainId = field(default_factory=new_uuid7)
    head_version_id: DomainId | None = None

    def move_head(self, version_id: DomainId) -> None:
        self.head_version_id = version_id


@dataclass(slots=True)
class AgentRun:
    organization_id: DomainId
    project_id: DomainId
    thread_id: str
    graph_version: str
    agent_config_version: str
    id: DomainId = field(default_factory=new_uuid7)
    status: AgentRunStatus = AgentRunStatus.PENDING
    budget: Budget = field(default_factory=Budget)

    def transition_to(self, target: AgentRunStatus) -> None:
        self.status = transition_agent_run(self.status, target)


@dataclass(slots=True)
class Task:
    organization_id: DomainId
    project_id: DomainId
    kind: str
    id: DomainId = field(default_factory=new_uuid7)
    status: TaskStatus = TaskStatus.PENDING
    dependency_ids: tuple[DomainId, ...] = ()

    def transition_to(self, target: TaskStatus) -> None:
        self.status = transition_task(self.status, target)


@dataclass(frozen=True, slots=True)
class Generation:
    organization_id: DomainId
    project_id: DomainId
    provider: str
    model: str
    paid: bool
    operation: OperationIdentity | None
    id: DomainId = field(default_factory=new_uuid7)
    provider_ref: ProviderRef | None = None

    def __post_init__(self) -> None:
        if self.paid and self.operation is None:
            raise InvariantViolation("paid generation requires operation/idempotency identity")


@dataclass(frozen=True, slots=True)
class CostEntry:
    organization_id: DomainId
    amount: Money
    category: str
    id: DomainId = field(default_factory=new_uuid7)
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reverses_entry_id: DomainId | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def reversal(self, *, reason: str) -> CostEntry:
        if not reason.strip():
            raise ValueError("reversal reason is required")
        return CostEntry(
            organization_id=self.organization_id,
            amount=Money(-self.amount.amount, self.amount.currency),
            category="reversal",
            reverses_entry_id=self.id,
            metadata={"reason": reason},
        )

    def adjustment(self, *, amount: Decimal, reason: str) -> CostEntry:
        if not reason.strip():
            raise ValueError("adjustment reason is required")
        return replace(
            self.reversal(reason=reason),
            amount=Money(amount, self.amount.currency),
            category="adjustment",
        )
