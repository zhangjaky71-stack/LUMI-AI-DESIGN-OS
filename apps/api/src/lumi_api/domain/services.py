from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .entities import ArtifactVersion, Brand, CostEntry, Generation, Project, Task
from .value_objects import Money


class ProjectService(Protocol):
    async def create(self, project: Project) -> Project: ...


class BrandPolicyService(Protocol):
    def assert_allowed(self, brand: Brand, operation_name: str) -> None: ...


class DesignOperationService(Protocol):
    async def apply(self, organization_id: UUID, document_id: UUID, operation: object) -> object: ...


class ArtifactVersionService(Protocol):
    async def create_version(self, version: ArtifactVersion) -> ArtifactVersion: ...


class TaskGraphService(Protocol):
    async def schedule(self, tasks: tuple[Task, ...]) -> tuple[Task, ...]: ...


class GenerationService(Protocol):
    async def execute(self, generation: Generation) -> Generation: ...


class CostLedgerService(Protocol):
    async def record(self, entry: CostEntry) -> None: ...

    async def balance(self, organization_id: UUID, currency: str) -> Money: ...


class ApprovalService(Protocol):
    async def approve_artifact_version(self, version_id: UUID, actor_id: UUID) -> ArtifactVersion: ...


class AccessPolicyService(Protocol):
    async def assert_member(self, organization_id: UUID, actor_id: UUID) -> None: ...
