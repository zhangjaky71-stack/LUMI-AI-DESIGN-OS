from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_agent_runtime.control_plane.client import GraphControlPlaneClient
from lumi_agent_runtime.control_plane.contracts import (
    GraphDefinition,
    GraphRunRequest,
    GraphRunStatus,
)
from lumi_agent_runtime.control_plane.control_plane import LangGraphControlPlane
from lumi_agent_runtime.control_plane.api import GraphControlPlaneAPI
from lumi_agent_runtime.control_plane.registry import GraphRegistry
from lumi_agent_runtime.control_plane.testing import (
    MemoryEventSink,
    MemoryGraphRunStore,
    MemoryOperationGuard,
    ScriptedGraphExecutor,
    StaticResumeAuthorizer,
    snapshot,
)


class ControlPlaneClientBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_starts_run_without_exposing_execution_internals(self) -> None:
        definition = GraphDefinition(
            graph_key="client.boundary",
            graph_version="1.0.0",
            agent_config_version="agent-v1",
            description="Client boundary graph",
            state_schema_version=1,
        )
        request = GraphRunRequest(
            organization_id=uuid4(),
            project_id=uuid4(),
            agent_run_id=uuid4(),
            operation_id=uuid4(),
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            agent_config_version=definition.agent_config_version,
            input={"brief": "test"},
            thread_id=f"thread-{uuid4()}",
        )
        executor = ScriptedGraphExecutor(
            [
                snapshot(
                    definition=definition,
                    request=request,
                    status=GraphRunStatus.SUCCEEDED,
                    checkpoint_id="cp-1",
                )
            ]
        )
        control = LangGraphControlPlane(
            registry=GraphRegistry((definition,)),
            executor=executor,
            store=MemoryGraphRunStore(),
            resume_authorizer=StaticResumeAuthorizer(),
            operation_guard=MemoryOperationGuard(),
            events=MemoryEventSink(),
        )
        client = GraphControlPlaneClient(GraphControlPlaneAPI(control))
        result = await client.start(request)
        self.assertEqual(result.status, GraphRunStatus.SUCCEEDED)
        for name in ("registry", "executor", "checkpointer", "graphs", "store"):
            self.assertFalse(hasattr(client, name), name)


if __name__ == "__main__":
    unittest.main()
