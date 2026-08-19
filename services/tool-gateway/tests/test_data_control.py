from __future__ import annotations

import unittest
from typing import Any
from uuid import uuid4

from lumi_tool_gateway.catalog import build_p0_registry
from lumi_tool_gateway.contracts import ToolPermissionContext, ToolRequest
from lumi_tool_gateway.data_control import HttpToolDataClient, ProjectQueryAdapter
from lumi_tool_gateway.errors import ToolDataControlUnavailableError, ToolInputValidationError
from lumi_tool_gateway.schema import SchemaValidator


class _CapturingClient(HttpToolDataClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://api.test.internal:8000", auth_secret="d" * 64)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, dict(payload)))
        return {
            "project_id": str(uuid4()),
            "name": "Canonical Project",
            "status": "active",
            "summary": {"goal": "launch"},
        }


def _request(*, query: str = "project.summary") -> ToolRequest:
    organization_id = uuid4()
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        actor_agent="design-agent",
        name="project.query",
        version="1.0.0",
        arguments={"query": query},
        purpose="Read the canonical project summary for the active task.",
        permission_context=ToolPermissionContext(
            organization_id=organization_id,
            actor_id="agent-runtime:design-agent",
            granted_permissions=frozenset({"tool.project.query"}),
            agent_allow_patterns=("project.*",),
            organization_allow_patterns=("project.*",),
        ),
    )


class ToolDataControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_derives_project_scope_from_task_without_project_argument(self) -> None:
        client = _CapturingClient()
        request = _request()
        result = await client.project_query(request)

        self.assertEqual(result["name"], "Canonical Project")
        self.assertEqual(len(client.calls), 1)
        path, payload = client.calls[0]
        self.assertEqual(path, "/internal/v1/tool-data/project/query")
        self.assertEqual(payload["organization_id"], str(request.organization_id))
        self.assertEqual(payload["agent_run_id"], str(request.agent_run_id))
        self.assertEqual(payload["task_id"], str(request.task_id))
        self.assertEqual(payload["query"], "project.summary")
        self.assertNotIn("project_id", payload)

    async def test_project_adapter_returns_canonical_summary(self) -> None:
        client = _CapturingClient()
        definition = build_p0_registry().resolve("project.query", "1.0.0")
        result = await ProjectQueryAdapter(client).invoke(definition, _request())

        self.assertEqual(result.data["name"], "Canonical Project")
        self.assertIn("Canonical Project", result.summary)

    async def test_client_rejects_unsupported_project_query(self) -> None:
        client = _CapturingClient()
        with self.assertRaises(ToolDataControlUnavailableError):
            await client.project_query(_request(query="project.delete"))
        self.assertEqual(client.calls, [])

    def test_catalog_rejects_legacy_project_id_and_unknown_query(self) -> None:
        definition = build_p0_registry().resolve("project.query", "1.0.0")
        validator = SchemaValidator()
        validator.validate_input(definition.input_schema, {"query": "project.summary"})
        with self.assertRaises(ToolInputValidationError):
            validator.validate_input(
                definition.input_schema,
                {"query": "project.summary", "project_id": str(uuid4())},
            )
        with self.assertRaises(ToolInputValidationError):
            validator.validate_input(definition.input_schema, {"query": "project.delete"})


if __name__ == "__main__":
    unittest.main()
