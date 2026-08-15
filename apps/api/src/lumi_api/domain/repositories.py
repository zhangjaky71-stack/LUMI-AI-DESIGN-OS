from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .entities import AgentRun, Artifact, Asset, CostEntry, Project, Task


class ProjectRepository(Protocol):
    async def get(self, project_id: UUID) -> Project | None: ...

    async def save(self, project: Project) -> None: ...


class AssetRepository(Protocol):
    async def get(self, asset_id: UUID) -> Asset | None: ...

    async def save(self, asset: Asset) -> None: ...


class ArtifactRepository(Protocol):
    async def get(self, artifact_id: UUID) -> Artifact | None: ...

    async def save(self, artifact: Artifact) -> None: ...


class TaskRepository(Protocol):
    async def get(self, task_id: UUID) -> Task | None: ...

    async def save(self, task: Task) -> None: ...


class AgentRunRepository(Protocol):
    async def get(self, run_id: UUID) -> AgentRun | None: ...

    async def save(self, run: AgentRun) -> None: ...


class CostLedgerRepository(Protocol):
    async def get(self, entry_id: UUID) -> CostEntry | None: ...

    async def append(self, entry: CostEntry) -> None: ...
