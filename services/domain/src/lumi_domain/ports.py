from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .entities import AgentRun, Artifact, Asset, CostEntry, Project, Task
from .ids import DomainId


class ProjectRepository(Protocol):
    def get(self, project_id: DomainId) -> Project | None: ...
    def save(self, project: Project) -> None: ...


class AssetRepository(Protocol):
    def get(self, asset_id: DomainId) -> Asset | None: ...
    def save(self, asset: Asset) -> None: ...


class ArtifactRepository(Protocol):
    def get(self, artifact_id: DomainId) -> Artifact | None: ...
    def save(self, artifact: Artifact) -> None: ...


class TaskRepository(Protocol):
    def get(self, task_id: DomainId) -> Task | None: ...
    def save(self, task: Task) -> None: ...
    def dependencies(self, task_id: DomainId) -> Iterable[DomainId]: ...


class AgentRunRepository(Protocol):
    def get(self, run_id: DomainId) -> AgentRun | None: ...
    def save(self, run: AgentRun) -> None: ...


class CostLedgerRepository(Protocol):
    def append(self, entry: CostEntry) -> None: ...
    def entries_for_organization(self, organization_id: DomainId) -> Iterable[CostEntry]: ...


class ProjectService(Protocol):
    def activate(self, project_id: DomainId) -> Project: ...


class BrandPolicyService(Protocol):
    def validate_brand(self, brand_id: DomainId) -> None: ...


class DesignOperationService(Protocol):
    def apply_operation(self, document_id: DomainId, operation_name: str) -> DomainId: ...


class ArtifactVersionService(Protocol):
    def create_version(self, artifact_id: DomainId, content_hash: str) -> DomainId: ...


class TaskGraphService(Protocol):
    def mark_ready(self, task_id: DomainId) -> Task: ...


class GenerationService(Protocol):
    def request_generation(self, project_id: DomainId) -> DomainId: ...


class CostLedgerService(Protocol):
    def record(self, entry: CostEntry) -> None: ...


class ApprovalService(Protocol):
    def approve(self, version_id: DomainId, actor_id: DomainId) -> None: ...


class AccessPolicyService(Protocol):
    def require_access(self, actor_id: DomainId, organization_id: DomainId) -> None: ...
