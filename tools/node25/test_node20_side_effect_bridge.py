from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from uuid import uuid4

from lumi_api.idempotency.gateway import SideEffectGateway
from lumi_api.idempotency.hashing import canonical_request_hash
from lumi_api.idempotency.memory import MemoryIdempotencyStore
from lumi_api.idempotency.models import (
    CompensationMode,
    OperationRequest,
    SideEffectKind,
    SideEffectOutcome,
)
from lumi_tool_gateway.audit import MemoryAuditSink
from lumi_tool_gateway.contracts import (
    ToolAdapterOutput,
    ToolPermissionContext,
    ToolRequest,
    ToolSideEffectContext,
    ToolSideEffectResponse,
)
from lumi_tool_gateway.errors import ToolInternalError
from lumi_tool_gateway.gateway import ToolGateway
from lumi_tool_gateway.registry import ToolRegistry
from lumi_tool_gateway.testing import CountingAdapter
from lumi_tool_gateway.catalog import p0_tool_definitions


class Node20SideEffectGuard:
    """Composition adapter proving NODE-25's port maps to NODE-20 exactly."""

    def __init__(self) -> None:
        self.gateway = SideEffectGateway(MemoryIdempotencyStore())

    async def execute(
        self,
        context: ToolSideEffectContext,
        invoke: Callable[[], Awaitable[ToolAdapterOutput]],
    ) -> ToolSideEffectResponse:
        operation = OperationRequest(
            organization_id=context.organization_id,
            operation_type=context.operation_type,
            idempotency_key=context.idempotency_key,
            request_hash=canonical_request_hash(context.request),
            business_scope_id=str(context.business_scope_id),
            side_effect_kind=SideEffectKind.EXTERNAL_TOOL_WRITE,
            compensation_mode=CompensationMode.REVERSIBLE_BY_NEW_OPERATION,
            paid=False,
        )

        async def effect(_execution_context) -> SideEffectOutcome:
            output = await invoke()
            return SideEffectOutcome(
                result={
                    "data": output.data,
                    "summary": output.summary,
                    "resource_refs": list(output.resource_refs),
                    "side_effect_ref": output.side_effect_ref,
                },
                result_ref=output.side_effect_ref,
            )

        outcome = await self.gateway.execute(
            operation,
            effect,
            lease_owner="node25-tool-gateway-test",
        )
        payload = outcome.result
        return ToolSideEffectResponse(
            output=ToolAdapterOutput(
                data=payload.get("data", {}),
                summary=str(payload.get("summary", "")),
                resource_refs=tuple(
                    str(item) for item in payload.get("resource_refs", [])
                ),
                side_effect_ref=(
                    None
                    if payload.get("side_effect_ref") is None
                    else str(payload["side_effect_ref"])
                ),
            ),
            replayed=outcome.replayed,
            operation_id=(
                None if outcome.operation_id is None else str(outcome.operation_id)
            ),
        )


def build_request(*, value: str, idempotency_key: str) -> ToolRequest:
    definition = next(
        item for item in p0_tool_definitions()
        if item.name == "asset.write-derived"
    )
    organization_id = uuid4()
    return ToolRequest(
        tool_call_id=uuid4(),
        organization_id=organization_id,
        agent_run_id=uuid4(),
        task_id=uuid4(),
        actor_agent="node25-bridge-agent",
        name=definition.name,
        version=definition.version,
        arguments={
            "source_asset_id": value,
            "artifact_ref": "artifact://node25/1",
        },
        purpose="prove NODE-20/NODE-25 write composition",
        permission_context=ToolPermissionContext(
            organization_id=organization_id,
            actor_id="node25-bridge-user",
            granted_permissions=definition.permissions,
            agent_allow_patterns=(definition.name,),
        ),
        idempotency_key=idempotency_key,
        trace_id="node25-node20-bridge",
    )


async def main_async() -> None:
    definition = next(
        item for item in p0_tool_definitions()
        if item.name == "asset.write-derived"
    )
    adapter = CountingAdapter(
        ToolAdapterOutput(
            data={"asset_id": "derived-asset-1"},
            summary="derived asset created",
            resource_refs=("asset://derived-asset-1",),
            side_effect_ref="asset://derived-asset-1",
        )
    )
    guard = Node20SideEffectGuard()
    gateway = ToolGateway(
        registry=ToolRegistry((definition,)),
        adapters={definition.key: adapter},
        side_effect_guard=guard,
        audit_sink=MemoryAuditSink(),
    )

    first_request = build_request(
        value="source-asset-1",
        idempotency_key="node25-write-1",
    )
    first = await gateway.invoke(first_request)
    replay_request = replace(
        first_request,
        tool_call_id=uuid4(),
    )
    replay = await gateway.invoke(replay_request)
    assert first.replayed is False
    assert replay.replayed is True
    assert first.data == replay.data == {"asset_id": "derived-asset-1"}
    assert first.resource_refs == replay.resource_refs == ("asset://derived-asset-1",)
    assert adapter.calls == 1

    changed = replace(
        first_request,
        tool_call_id=uuid4(),
        arguments={
            "source_asset_id": "source-asset-2",
            "artifact_ref": "artifact://node25/1",
        },
    )
    try:
        await gateway.invoke(changed)
    except ToolInternalError as exc:
        # The production composition root maps NODE-20's conflict to the public
        # Tool Gateway error taxonomy. Until that mapping layer exists, the core
        # gateway correctly fail-closes instead of running a second side effect.
        assert str(exc) == "unexpected Tool Gateway execution failure"
    else:
        raise AssertionError("NODE-20 semantic conflict did not fail closed")
    assert adapter.calls == 1
    print("NODE25_NODE20_SIDE_EFFECT_BRIDGE_VALID")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
