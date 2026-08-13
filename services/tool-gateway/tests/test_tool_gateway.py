from __future__ import annotations

import asyncio
import unittest
from uuid import uuid4

from lumi_tool_gateway.audit import MemoryAuditSink
from lumi_tool_gateway.contracts import (
    ApprovalDecision,
    ToolAdapterOutput,
    ToolCallStatus,
    ToolDefinition,
    ToolIdempotency,
    ToolPermissionContext,
    ToolRequest,
    ToolRisk,
    ToolRuntime,
)
from lumi_tool_gateway.errors import (
    ToolAdapterExecutionError,
    ToolIdempotencyRequiredError,
    ToolInputValidationError,
    ToolOutputValidationError,
    ToolPermissionDeniedError,
    ToolSideEffectGuardRequiredError,
    ToolTimeoutError,
)
from lumi_tool_gateway.gateway import ToolGateway
from lumi_tool_gateway.registry import ToolRegistry
from lumi_tool_gateway.testing import (
    CountingAdapter,
    MemoryIdempotentSideEffectGuard,
    MemoryResultOffloader,
    StaticApprovalResolver,
)


def definition(
    *,
    name: str = "project.query",
    version: str = "1.0.0",
    risk: ToolRisk = ToolRisk.READ_INTERNAL,
    idempotency: ToolIdempotency = ToolIdempotency.NOT_REQUIRED,
    timeout: float = 1.0,
    output_schema=None,
    max_inline: int = 64 * 1024,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        version=version,
        description="test tool",
        input_schema={
            "type": "object",
            "required": ["value"],
            "properties": {
                "value": {"type": "string"},
                "api_key": {"type": "string"},
            },
            "additionalProperties": False,
        },
        output_schema=output_schema
        or {
            "type": "object",
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
            "additionalProperties": False,
        },
        risk=risk,
        idempotency=idempotency,
        permissions=frozenset({f"tool.{name}"}),
        runtime=ToolRuntime.NATIVE,
        timeout_seconds=timeout,
        max_inline_output_bytes=max_inline,
    )


def request(
    tool: ToolDefinition,
    *,
    patterns: tuple[str, ...] | None = None,
    parent_patterns: tuple[str, ...] | None = None,
    permissions: frozenset[str] | None = None,
    arguments=None,
    idempotency_key: str | None = None,
) -> ToolRequest:
    organization_id = uuid4()
    context = ToolPermissionContext(
        organization_id=organization_id,
        actor_id="user-1",
        granted_permissions=permissions or tool.permissions,
        agent_allow_patterns=(tool.name,) if patterns is None else patterns,
        parent_allow_patterns=parent_patterns,
    )
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        actor_agent="planner",
        name=tool.name,
        version=tool.version,
        arguments=arguments or {"value": "hello"},
        purpose="test gateway behavior",
        permission_context=context,
        idempotency_key=idempotency_key,
        trace_id="trace-1",
    )


class ToolGatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_registry_resolves_exact_and_major_version(self) -> None:
        v1 = definition(version="1.0.0")
        v11 = definition(version="1.1.0")
        v2 = definition(version="2.0.0")
        registry = ToolRegistry((v1, v11, v2))
        self.assertEqual(registry.resolve(v1.name, "1.0.0").version, "1.0.0")
        self.assertEqual(registry.resolve(v1.name, "1.x").version, "1.1.0")
        self.assertEqual(registry.resolve(v1.name, "2.x").version, "2.0.0")

    def test_write_definition_cannot_disable_idempotency(self) -> None:
        with self.assertRaisesRegex(ValueError, "TOOL_WRITE_IDEMPOTENCY_REQUIRED"):
            definition(
                name="asset.write-derived",
                risk=ToolRisk.WRITE_INTERNAL,
                idempotency=ToolIdempotency.NOT_REQUIRED,
            )

    async def test_empty_agent_allowlist_is_default_deny(self) -> None:
        tool = definition()
        adapter = CountingAdapter(ToolAdapterOutput(data={"ok": True}))
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
        )
        with self.assertRaisesRegex(ToolPermissionDeniedError, "AGENT_TOOL_NOT_ALLOWED"):
            await gateway.invoke(request(tool, patterns=()))
        self.assertEqual(adapter.calls, 0)

    async def test_input_schema_failure_happens_before_adapter(self) -> None:
        tool = definition()
        adapter = CountingAdapter(ToolAdapterOutput(data={"ok": True}))
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
        )
        with self.assertRaises(ToolInputValidationError):
            await gateway.invoke(request(tool, arguments={"value": 7}))
        self.assertEqual(adapter.calls, 0)

    async def test_default_deny_forbidden_tool(self) -> None:
        tool = definition()
        adapter = CountingAdapter(ToolAdapterOutput(data={"ok": True}))
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
        )
        with self.assertRaises(ToolPermissionDeniedError):
            await gateway.invoke(request(tool, patterns=("asset.*",)))
        self.assertEqual(adapter.calls, 0)

    async def test_subagent_cannot_expand_parent_tool_scope(self) -> None:
        tool = definition()
        adapter = CountingAdapter(ToolAdapterOutput(data={"ok": True}))
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
        )
        with self.assertRaisesRegex(
            ToolPermissionDeniedError,
            "SUBAGENT_PERMISSION_ESCALATION",
        ):
            await gateway.invoke(
                request(
                    tool,
                    patterns=(tool.name,),
                    parent_patterns=("asset.*",),
                )
            )
        self.assertEqual(adapter.calls, 0)

    async def test_subagent_with_empty_parent_scope_has_no_tools(self) -> None:
        tool = definition()
        adapter = CountingAdapter(ToolAdapterOutput(data={"ok": True}))
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
        )
        with self.assertRaisesRegex(
            ToolPermissionDeniedError,
            "SUBAGENT_PERMISSION_ESCALATION",
        ):
            await gateway.invoke(
                request(
                    tool,
                    patterns=(tool.name,),
                    parent_patterns=(),
                )
            )
        self.assertEqual(adapter.calls, 0)

    async def test_external_write_requires_approval_before_adapter(self) -> None:
        tool = definition(
            name="publish.external",
            risk=ToolRisk.WRITE_EXTERNAL,
            idempotency=ToolIdempotency.REQUIRED,
        )
        adapter = CountingAdapter(ToolAdapterOutput(data={"ok": True}))
        guard = MemoryIdempotentSideEffectGuard()
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
            side_effect_guard=guard,
        )
        result = await gateway.invoke(request(tool, idempotency_key="publish-1"))
        self.assertEqual(result.status, ToolCallStatus.APPROVAL_REQUIRED)
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(guard.invocations, 0)

    async def test_approved_write_is_idempotent_and_replays(self) -> None:
        tool = definition(
            name="publish.external",
            risk=ToolRisk.WRITE_EXTERNAL,
            idempotency=ToolIdempotency.REQUIRED,
        )
        adapter = CountingAdapter(
            ToolAdapterOutput(data={"ok": True}, side_effect_ref="ext://1")
        )
        guard = MemoryIdempotentSideEffectGuard()
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
            approval_resolver=StaticApprovalResolver(ApprovalDecision.APPROVED),
            side_effect_guard=guard,
        )
        req = request(tool, idempotency_key="publish-1")
        first = await gateway.invoke(req)
        second = await gateway.invoke(req)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(guard.invocations, 1)
        self.assertEqual(guard.replays, 1)

    async def test_required_idempotency_key_and_guard_fail_closed(self) -> None:
        tool = definition(
            name="asset.write-derived",
            risk=ToolRisk.WRITE_INTERNAL,
            idempotency=ToolIdempotency.REQUIRED,
        )
        adapter = CountingAdapter(ToolAdapterOutput(data={"ok": True}))
        without_guard = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
        )
        with self.assertRaises(ToolIdempotencyRequiredError):
            await without_guard.invoke(request(tool))
        with self.assertRaises(ToolSideEffectGuardRequiredError):
            await without_guard.invoke(request(tool, idempotency_key="write-1"))
        self.assertEqual(adapter.calls, 0)

    async def test_large_output_is_offloaded(self) -> None:
        tool = definition(
            output_schema={
                "type": "object",
                "required": ["text"],
                "properties": {"text": {"type": "string"}},
                "additionalProperties": False,
            },
            max_inline=1024,
        )
        adapter = CountingAdapter(ToolAdapterOutput(data={"text": "x" * 5000}))
        offloader = MemoryResultOffloader()
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
            result_offloader=offloader,
        )
        result = await gateway.invoke(request(tool))
        self.assertTrue(result.truncated)
        self.assertIsNotNone(result.full_result_ref)
        self.assertIn(result.full_result_ref or "", offloader.objects)
        self.assertLess(len(str(result.data)), 5000)

    async def test_invalid_adapter_output_is_rejected(self) -> None:
        tool = definition()
        adapter = CountingAdapter(ToolAdapterOutput(data={"ok": "yes"}))
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
        )
        with self.assertRaises(ToolOutputValidationError):
            await gateway.invoke(request(tool))

    async def test_timeout_is_normalized(self) -> None:
        tool = definition(timeout=0.1)

        class SlowAdapter:
            async def invoke(self, definition, request):
                del definition, request
                await asyncio.sleep(1)
                return ToolAdapterOutput(data={"ok": True})

        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: SlowAdapter()},
        )
        with self.assertRaises(ToolTimeoutError):
            await gateway.invoke(request(tool))

    async def test_adapter_exception_is_normalized_and_audited(self) -> None:
        tool = definition()
        audit = MemoryAuditSink()

        class BrokenAdapter:
            async def invoke(self, definition, request):
                del definition, request
                raise RuntimeError("provider secret should not leak")

        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: BrokenAdapter()},
            audit_sink=audit,
        )
        with self.assertRaises(ToolAdapterExecutionError):
            await gateway.invoke(request(tool))
        self.assertEqual(
            audit.records[-1].error_code,
            "TOOL_ADAPTER_EXECUTION_ERROR",
        )
        self.assertNotIn("provider secret", repr(audit.records[-1]))

    async def test_audit_redacts_secret_like_fields(self) -> None:
        tool = definition()
        adapter = CountingAdapter(ToolAdapterOutput(data={"ok": True}))
        audit = MemoryAuditSink()
        gateway = ToolGateway(
            registry=ToolRegistry((tool,)),
            adapters={tool.key: adapter},
            audit_sink=audit,
        )
        await gateway.invoke(
            request(tool, arguments={"value": "ok", "api_key": "super-secret"})
        )
        self.assertEqual(audit.records[-1].arguments["api_key"], "[REDACTED]")
        self.assertNotIn("super-secret", repr(audit.records[-1]))


if __name__ == "__main__":
    unittest.main()
