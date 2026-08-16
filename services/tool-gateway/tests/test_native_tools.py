from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_tool_gateway.catalog import build_p0_registry, p0_tool_definitions
from lumi_tool_gateway.contracts import (
    ToolIdempotency,
    ToolPermissionContext,
    ToolRequest,
)
from lumi_tool_gateway.native import SandboxExecuteAdapter, WebSearchAdapter


class FakeSearchBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, *, limit: int):
        self.calls.append((query, limit))
        return [
            {
                "title": f"Result {index}",
                "url": f"https://example.com/{index}",
                "snippet": "public information",
            }
            for index in range(limit + 3)
        ]


class FakeSandboxExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}


def request(name: str, arguments: dict[str, object]) -> ToolRequest:
    definition = build_p0_registry().resolve(name, "1.0.0")
    organization_id = uuid4()
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        actor_agent="worker",
        name=definition.name,
        version=definition.version,
        arguments=arguments,
        purpose="native adapter test",
        permission_context=ToolPermissionContext(
            organization_id=organization_id,
            actor_id="user-1",
            granted_permissions=definition.permissions,
            agent_allow_patterns=(definition.name,),
        ),
        idempotency_key=("sandbox-run-1" if name == "sandbox.execute" else None),
    )


class NativeToolTests(unittest.IsolatedAsyncioTestCase):
    def test_p0_catalog_is_exact_and_all_writes_require_idempotency(self) -> None:
        definitions = p0_tool_definitions()
        self.assertEqual(
            {item.name for item in definitions},
            {
                "web.search",
                "web.fetch",
                "asset.read",
                "asset.write-derived",
                "project.query",
                "artifact.query",
                "sandbox.execute",
                "media.inspect",
            },
        )
        self.assertEqual(len(definitions), 8)
        for item in definitions:
            if item.is_write:
                self.assertEqual(item.idempotency, ToolIdempotency.REQUIRED)
        self.assertNotIn("sql", " ".join(item.name for item in definitions).lower())

    async def test_web_search_normalizes_and_caps_backend_rows(self) -> None:
        backend = FakeSearchBackend()
        adapter = WebSearchAdapter(backend)
        definition = build_p0_registry().resolve("web.search", "1.0.0")
        result = await adapter.invoke(
            definition,
            request("web.search", {"query": "design systems", "limit": 3}),
        )
        self.assertEqual(backend.calls, [("design systems", 3)])
        self.assertEqual(len(result.data["results"]), 3)
        self.assertTrue(result.data["results"][0]["url"].startswith("https://"))

    async def test_sandbox_adapter_uses_isolated_executor_port(self) -> None:
        executor = FakeSandboxExecutor()
        adapter = SandboxExecuteAdapter(executor)
        definition = build_p0_registry().resolve("sandbox.execute", "1.0.0")
        req = request("sandbox.execute", {"command": ["python", "-V"]})
        result = await adapter.invoke(definition, req)
        self.assertEqual(result.data["exit_code"], 0)
        self.assertEqual(len(executor.calls), 1)
        call = executor.calls[0]
        self.assertEqual(call["organization_id"], str(req.organization_id))
        self.assertEqual(call["agent_run_id"], str(req.agent_run_id))
        self.assertEqual(call["task_id"], str(req.task_id))
        self.assertEqual(call["command"], ["python", "-V"])
        self.assertEqual(call["timeout_seconds"], definition.timeout_seconds)

    async def test_sandbox_adapter_rejects_string_shell_command(self) -> None:
        executor = FakeSandboxExecutor()
        adapter = SandboxExecuteAdapter(executor)
        definition = build_p0_registry().resolve("sandbox.execute", "1.0.0")
        req = request("sandbox.execute", {"command": "python -V"})
        with self.assertRaisesRegex(ValueError, "TOOL_SANDBOX_COMMAND_INVALID"):
            await adapter.invoke(definition, req)
        self.assertEqual(executor.calls, [])


if __name__ == "__main__":
    unittest.main()
