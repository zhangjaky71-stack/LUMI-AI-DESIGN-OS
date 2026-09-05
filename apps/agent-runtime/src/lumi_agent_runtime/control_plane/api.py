from __future__ import annotations

from uuid import UUID

from .contracts import GraphRunRequest, GraphRunSnapshot, ResumeRequest
from .control_plane import LangGraphControlPlane


class GraphControlPlaneAPI:
    """Transport-neutral server boundary; no graph/checkpointer internals are exposed."""

    def __init__(self, control_plane: LangGraphControlPlane) -> None:
        self._control_plane = control_plane

    async def start(self, request: GraphRunRequest) -> GraphRunSnapshot:
        return await self._control_plane.start(request)

    async def resume(self, request: ResumeRequest) -> GraphRunSnapshot:
        return await self._control_plane.resume(request)

    async def snapshot(self, agent_run_id: UUID) -> GraphRunSnapshot:
        return await self._control_plane.snapshot(agent_run_id)

    async def cancel(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        agent_run_id: UUID,
        operation_id: UUID,
        trace_id: str | None = None,
    ) -> GraphRunSnapshot:
        return await self._control_plane.cancel(
            organization_id=organization_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
            operation_id=operation_id,
            trace_id=trace_id,
        )
