from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .entities import AgentRun, Artifact, Asset, CostEntry, Project, Task


class ProjectRepository(Protocol):
    async def get(self, organization_id: UUID, project_id: UUID) -> Project | None: ...

    async def save(self, organization_id: UUID, project: Project) -> None: ...


class AssetRepository(Protocol):
    async def get(self, organization_id: UUID, asset_id: UUID) -> Asset | None: ...

    async def save(self, organization_id: UUID, asset: Asset) -> None: ...


class ArtifactRepository(Protocol):
    async def get(self, organization_id: UUID, artifact_id: UUID) -> Artifact | None: ...

    async def save(self, organization_id: UUID, artifact: Artifact) -> None: ...


class TaskRepository(Protocol):
    async def get(self, organization_id: UUID, task_id: UUID) -> Task | None: ...

    async def save(self, organization_id: UUID, task: Task) -> None: ...


class AgentRunRepository(Protocol):
    async def get(self, organization_id: UUID, run_id: UUID) -> AgentRun | None: ...

    async def save(self, organization_id: UUID, run: AgentRun) -> None: ...


class CostLedgerRepository(Protocol):
    async def get(self, organization_id: UUID, entry_id: UUID) -> CostEntry | None: ...

    async def append(self, organization_id: UUID, entry: CostEntry) -> None: ...
