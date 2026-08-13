from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from lumi_tool_gateway.audit import MemoryAuditSink
from lumi_tool_gateway.catalog import build_p0_registry
from lumi_tool_gateway.contracts import (
    ToolAdapterOutput,
    ToolCallStatus,
    ToolPermissionContext,
    ToolRequest,
)
from lumi_tool_gateway.errors import ToolPermissionDeniedError, ToolSSRFBlockedError
from lumi_tool_gateway.gateway import ToolGateway
from lumi_tool_gateway.native import (
    HTTPTransportResponse,
    NativeFunctionAdapter,
    SafeWebFetchAdapter,
    SandboxExecuteAdapter,
    WebSearchAdapter,
)
from lumi_tool_gateway.ssrf import SSRFPolicy
from lumi_tool_gateway.testing import MemoryIdempotentSideEffectGuard, MemoryResultOffloader


class SearchBackend:
    async def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "title": f"{query} result {index}",
                "url": f"https://example.com/{index}",
                "snippet": "deterministic fixture",
            }
            for index in range(limit)
        ]


class Resolver:
    def resolve(self, hostname: str) -> tuple[str, ...]:
        if hostname == "public.example":
            return ("8.8.8.8",)
        raise AssertionError(f"unexpected DNS lookup: {hostname}")


class Transport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def fetch(self, **kwargs) -> HTTPTransportResponse:
        self.calls.append(dict(kwargs))
        return HTTPTransportResponse(
            status=200,
            headers={"Content-Type": "text/plain; charset=utf-8"},
            body=("research " * 14000).encode(),
        )


class RedirectTransport:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, **kwargs) -> HTTPTransportResponse:
        del kwargs
        self.calls += 1
        return HTTPTransportResponse(
            status=302,
            headers={"Location": "http://169.254.169.254/latest/meta-data/"},
            body=b"",
        )


class SandboxExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, **kwargs) -> dict[str, Any]:
        self.calls += 1
        return {
            "exit_code": 0,
            "stdout": "Python 3.12",
            "stderr": "",
            "sandbox_scope": {
                "organization_id": kwargs["organization_id"],
                "task_id": kwargs["task_id"],
            },
        }


class DerivedAssetHandler:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, definition, request) -> ToolAdapterOutput:
        del definition
        self.calls += 1
        return ToolAdapterOutput(
            data={
                "asset_id": f"derived-{request.arguments['source_asset_id']}",
                "artifact_ref": request.arguments["artifact_ref"],
            },
            summary="Derived Asset created through trusted storage adapter.",
            side_effect_ref="asset://derived",
        )


def permission_context(
    organization_id: UUID,
    *,
    parent_patterns: tuple[str, ...] = (),
) -> ToolPermissionContext:
    registry = build_p0_registry()
    permissions = frozenset(
        permission
        for definition in registry.definitions()
        for permission in definition.permissions
    )
    return ToolPermissionContext(
        organization_id=organization_id,
        actor_id="integration-user",
        granted_permissions=permissions,
        agent_allow_patterns=("web.*", "asset.*", "project.*", "artifact.*", "sandbox.*", "media.*"),
        parent_allow_patterns=parent_patterns,
    )


def make_request(
    name: str,
    arguments: dict[str, Any],
    *,
    organization_id: UUID,
    operation_key: str | None = None,
    parent_patterns: tuple[str, ...] = (),
    tool_call_id: UUID | None = None,
    task_id: UUID | None = None,
) -> ToolRequest:
    definition = build_p0_registry().resolve(name, "1.0.0")
    return ToolRequest(
        tool_call_id=tool_call_id or uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=task_id or uuid4(),
        actor_agent="integration-agent",
        name=definition.name,
        version=definition.version,
        arguments=arguments,
        purpose=f"NODE-25 integration for {name}",
        permission_context=permission_context(
            organization_id,
            parent_patterns=parent_patterns,
        ),
        idempotency_key=operation_key,
        trace_id="node25-integration",
    )


async def main_async() -> None:
    registry = build_p0_registry()
    assert len(registry.definitions()) == 8

    transport = Transport()
    asset_handler = DerivedAssetHandler()
    sandbox_executor = SandboxExecutor()
    adapters = {
        "web.search@1.0.0": WebSearchAdapter(SearchBackend()),
        "web.fetch@1.0.0": SafeWebFetchAdapter(
            transport,
            ssrf_policy=SSRFPolicy(resolver=Resolver()),
        ),
        "asset.write-derived@1.0.0": NativeFunctionAdapter(asset_handler),
        "project.query@1.0.0": NativeFunctionAdapter(
            lambda definition, request: _async_output(
                ToolAdapterOutput(
                    data={"query": request.arguments["query"], "rows": []},
                    summary="Tenant-scoped domain query fixture.",
                )
            )
        ),
        "sandbox.execute@1.0.0": SandboxExecuteAdapter(sandbox_executor),
    }
    guard = MemoryIdempotentSideEffectGuard()
    offloader = MemoryResultOffloader()
    audit = MemoryAuditSink()
    gateway = ToolGateway(
        registry=registry,
        adapters=adapters,
        side_effect_guard=guard,
        result_offloader=offloader,
        audit_sink=audit,
    )
    organization_id = uuid4()

    search = await gateway.invoke(
        make_request(
            "web.search",
            {"query": "LUMI design systems", "limit": 3},
            organization_id=organization_id,
        )
    )
    assert search.status == ToolCallStatus.SUCCEEDED
    assert len(search.data["results"]) == 3

    fetched = await gateway.invoke(
        make_request(
            "web.fetch",
            {"url": "https://public.example/research"},
            organization_id=organization_id,
        )
    )
    assert fetched.status == ToolCallStatus.SUCCEEDED
    assert fetched.truncated is True
    assert fetched.full_result_ref in offloader.objects
    assert transport.calls[0]["resolved_ip"] == "8.8.8.8"

    await gateway.invoke(
        make_request(
            "project.query",
            {"query": "project.summary", "parameters": {}},
            organization_id=organization_id,
        )
    )

    task_id = uuid4()
    first_write = make_request(
        "asset.write-derived",
        {"source_asset_id": "asset-1", "artifact_ref": "artifact://1"},
        organization_id=organization_id,
        operation_key="asset-derived-1",
        task_id=task_id,
    )
    replay_write = ToolRequest(
        tool_call_id=uuid4(),
        organization_id=first_write.organization_id,
        agent_run_id=first_write.agent_run_id,
        task_id=first_write.task_id,
        actor_agent=first_write.actor_agent,
        name=first_write.name,
        version=first_write.version,
        arguments=first_write.arguments,
        purpose=first_write.purpose,
        permission_context=first_write.permission_context,
        idempotency_key=first_write.idempotency_key,
        trace_id=first_write.trace_id,
    )
    first = await gateway.invoke(first_write)
    replay = await gateway.invoke(replay_write)
    assert first.replayed is False
    assert replay.replayed is True
    assert asset_handler.calls == 1

    sandbox = await gateway.invoke(
        make_request(
            "sandbox.execute",
            {"command": ["python", "-V"]},
            organization_id=organization_id,
            operation_key="sandbox-1",
        )
    )
    assert sandbox.data["exit_code"] == 0
    assert sandbox_executor.calls == 1

    try:
        await gateway.invoke(
            make_request(
                "web.search",
                {"query": "forbidden child"},
                organization_id=organization_id,
                parent_patterns=("asset.*",),
            )
        )
    except ToolPermissionDeniedError as exc:
        assert "SUBAGENT_PERMISSION_ESCALATION" in str(exc)
    else:
        raise AssertionError("subagent tool-scope escalation was not denied")

    redirect_transport = RedirectTransport()
    redirect_adapter = SafeWebFetchAdapter(
        redirect_transport,
        ssrf_policy=SSRFPolicy(resolver=Resolver()),
    )
    fetch_definition = registry.resolve("web.fetch", "1.0.0")
    try:
        await redirect_adapter.invoke(
            fetch_definition,
            make_request(
                "web.fetch",
                {"url": "https://public.example/start"},
                organization_id=organization_id,
            ),
        )
    except ToolSSRFBlockedError:
        pass
    else:
        raise AssertionError("redirect to metadata IP was not blocked")
    assert redirect_transport.calls == 1

    assert guard.invocations == 2
    assert guard.replays == 1
    assert audit.records
    assert all(record.organization_id == str(organization_id) for record in audit.records)
    print(
        "NODE-25 Tool Gateway integration: PASS "
        f"audit={len(audit.records)} offloaded={len(offloader.objects)} "
        f"side_effect_invocations={guard.invocations} replays={guard.replays}"
    )


async def _async_output(output: ToolAdapterOutput) -> ToolAdapterOutput:
    return output


def main() -> int:
    asyncio.run(main_async())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
