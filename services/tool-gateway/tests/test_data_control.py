from __future__ import annotations

import unittest
from typing import Any
from uuid import uuid4

from lumi_tool_gateway.catalog import build_p0_registry
from lumi_tool_gateway.contracts import ToolPermissionContext, ToolRequest
from lumi_tool_gateway.data_control import (
    ArtifactQueryAdapter,
    AssetReadAdapter,
    AssetWriteDerivedAdapter,
    HttpToolDataClient,
    MediaInspectAdapter,
    ProjectQueryAdapter,
)
from lumi_tool_gateway.errors import (
    ToolDataControlUnavailableError,
    ToolInputValidationError,
)
from lumi_tool_gateway.schema import SchemaValidator


class _CapturingClient(HttpToolDataClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://api.test.internal:8000", auth_secret="d" * 64)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, dict(payload)))
        if path.endswith("/project/query"):
            return {
                "project_id": str(uuid4()),
                "name": "Canonical Project",
                "status": "active",
                "summary": {"goal": "launch"},
            }
        if path.endswith("/artifact/query"):
            return {
                "artifact_id": str(payload["artifact_id"]),
                "project_id": str(uuid4()),
                "kind": "poster",
                "title": "Poster",
                "metadata": {},
                "latest_version": None,
            }
        if path.endswith("/asset/write-derived"):
            return {
                "asset_id": str(uuid4()),
                "project_id": str(uuid4()),
                "kind": "image",
                "source": "derived",
                "name": "derived.png",
                "status": "ready",
                "metadata": dict(payload.get("metadata", {})),
                "files": [],
            }
        return {
            "asset_id": str(payload["asset_id"]),
            "kind": "image",
            "status": "ready",
            "files": [],
            "metadata": {},
        }


def _request(
    *,
    name: str = "project.query",
    arguments: dict[str, Any] | None = None,
    permission: str = "tool.project.query",
    idempotency_key: str | None = None,
) -> ToolRequest:
    organization_id = uuid4()
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        actor_agent="design-agent",
        name=name,
        version="1.0.0",
        arguments=arguments or {"query": "project.summary"},
        purpose="Use canonical task-scoped data.",
        permission_context=ToolPermissionContext(
            organization_id=organization_id,
            actor_id="agent-runtime:design-agent",
            granted_permissions=frozenset({permission}),
            agent_allow_patterns=("*",),
            organization_allow_patterns=("*",),
        ),
        idempotency_key=idempotency_key,
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
        self.assertTrue(result.resource_refs[0].startswith("project://"))

    async def test_asset_artifact_and_media_clients_send_task_scope(self) -> None:
        client = _CapturingClient()
        asset_id = str(uuid4())
        artifact_id = str(uuid4())
        asset_request = _request(
            name="asset.read",
            arguments={"asset_id": asset_id},
            permission="tool.asset.read",
        )
        artifact_request = _request(
            name="artifact.query",
            arguments={"artifact_id": artifact_id},
            permission="tool.artifact.query",
        )
        media_request = _request(
            name="media.inspect",
            arguments={"asset_id": asset_id},
            permission="tool.media.inspect",
        )

        await client.asset_read(asset_request)
        await client.artifact_query(artifact_request)
        await client.media_inspect(media_request)

        self.assertEqual(len(client.calls), 3)
        for _, payload in client.calls:
            self.assertIn("organization_id", payload)
            self.assertIn("agent_run_id", payload)
            self.assertIn("task_id", payload)
            self.assertNotIn("project_id", payload)
        self.assertEqual(client.calls[0][1]["asset_id"], asset_id)
        self.assertEqual(client.calls[1][1]["artifact_id"], artifact_id)
        self.assertEqual(client.calls[2][1]["asset_id"], asset_id)

    async def test_read_adapters_return_internal_resource_refs(self) -> None:
        client = _CapturingClient()
        asset_id = str(uuid4())
        artifact_id = str(uuid4())
        registry = build_p0_registry()

        asset_result = await AssetReadAdapter(client).invoke(
            registry.resolve("asset.read", "1.0.0"),
            _request(
                name="asset.read",
                arguments={"asset_id": asset_id},
                permission="tool.asset.read",
            ),
        )
        artifact_result = await ArtifactQueryAdapter(client).invoke(
            registry.resolve("artifact.query", "1.0.0"),
            _request(
                name="artifact.query",
                arguments={"artifact_id": artifact_id},
                permission="tool.artifact.query",
            ),
        )
        media_result = await MediaInspectAdapter(client).invoke(
            registry.resolve("media.inspect", "1.0.0"),
            _request(
                name="media.inspect",
                arguments={"asset_id": asset_id},
                permission="tool.media.inspect",
            ),
        )

        self.assertEqual(asset_result.resource_refs, (f"asset://{asset_id}",))
        self.assertEqual(artifact_result.resource_refs, (f"artifact://{artifact_id}",))
        self.assertEqual(media_result.resource_refs, (f"asset://{asset_id}",))

    async def test_derived_asset_client_sends_canonical_side_effect_scope(self) -> None:
        client = _CapturingClient()
        source_asset_id = str(uuid4())
        artifact_id = uuid4()
        request = _request(
            name="asset.write-derived",
            arguments={
                "source_asset_id": source_asset_id,
                "artifact_ref": f"artifact://{artifact_id}",
                "metadata": {"variant": "social"},
            },
            permission="tool.asset.write-derived",
            idempotency_key="derived-1",
        )
        await client.asset_write_derived(request)

        path, payload = client.calls[0]
        self.assertEqual(path, "/internal/v1/tool-data/asset/write-derived")
        self.assertEqual(payload["tool_call_id"], str(request.tool_call_id))
        self.assertEqual(payload["source_asset_id"], source_asset_id)
        self.assertEqual(payload["artifact_ref"], f"artifact://{artifact_id}")
        self.assertEqual(payload["metadata"], {"variant": "social"})
        self.assertNotIn("project_id", payload)

    async def test_derived_asset_adapter_returns_durable_side_effect_ref(self) -> None:
        client = _CapturingClient()
        request = _request(
            name="asset.write-derived",
            arguments={
                "source_asset_id": str(uuid4()),
                "artifact_ref": f"artifact://{uuid4()}",
            },
            permission="tool.asset.write-derived",
            idempotency_key="derived-2",
        )
        definition = build_p0_registry().resolve("asset.write-derived", "1.0.0")
        result = await AssetWriteDerivedAdapter(client).invoke(definition, request)

        self.assertEqual(result.resource_refs, (result.side_effect_ref,))
        self.assertIsNotNone(result.side_effect_ref)
        self.assertTrue(result.side_effect_ref.startswith("asset://"))

    async def test_client_rejects_unsupported_project_query(self) -> None:
        client = _CapturingClient()
        with self.assertRaises(ToolDataControlUnavailableError):
            await client.project_query(_request(arguments={"query": "project.delete"}))
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
