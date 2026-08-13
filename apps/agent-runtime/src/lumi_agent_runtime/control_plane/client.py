from __future__ import annotations

from uuid import UUID

from .api import GraphControlPlaneAPI
from .contracts import GraphRunRequest, GraphRunSnapshot, ResumeRequest


class GraphControlPlaneClient:
    """Agent/API-facing client; intentionally exposes no registry/executor/checkpointer."""

    def __init__(self, api: GraphControlPlaneAPI) -> None:
        self._api = api

    async def start(self, request: GraphRunRequest) -> GraphRunSnapshot:
        return await self._api.start(request)

    async def resume(self, request: ResumeRequest) -> GraphRunSnapshot:
        return await self._api.resume(request)

    async def snapshot(self, agent_run_id: UUID) -> GraphRunSnapshot:
        return await self._api.snapshot(agent_run_id)

    async def cancel(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        operation_id: UUID,
        trace_id: str | None = None,
    ) -> GraphRunSnapshot:
        return await self._api.cancel(
            organization_id=organization_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
            operation_id=operation_id,
            trace_id=trace_id,
        )
