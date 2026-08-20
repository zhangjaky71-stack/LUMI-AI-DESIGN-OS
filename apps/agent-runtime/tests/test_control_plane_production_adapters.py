from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from lumi_agent_runtime.control_plane.contracts import (
    GraphRunEvent,
    GraphRunSnapshot,
    GraphRunStatus,
)
from lumi_agent_runtime.control_plane.errors import GraphResumeDeniedError
from lumi_agent_runtime.control_plane.production_adapters import (
    AgentControlUnavailableError,
    RemoteApprovalDecisionReader,
    RemoteControlPlaneOperationGuard,
    RemoteGraphEventSink,
    _snapshot_payload,
)


class _FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, payload))
        if not self.responses:
            raise AssertionError("unexpected control request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        assert isinstance(response, dict)
        return response


def _snapshot() -> GraphRunSnapshot:
    now = datetime.now(UTC)
    return GraphRunSnapshot(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        task_id=uuid4(),
        thread_id="thread-1",
        graph_key="design.root",
        graph_version="1.0.0",
        agent_config_version="1.0.0",
        status=GraphRunStatus.SUCCEEDED,
        checkpoint_id="cp-1",
        checkpoint_namespace="",
        state_values={"answer": "ok"},
        next_nodes=(),
        interrupts=(),
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_operation_guard_execute_commits_snapshot_once() -> None:
    snapshot = _snapshot()
    ledger_id = uuid4()
    client = _FakeClient(
        [
            {
                "decision": "execute",
                "ledger_operation_id": str(ledger_id),
                "lease_owner": "agent-runtime:lease",
                "result_json": {},
                "error_code": None,
            },
            {"status": "succeeded"},
        ]
    )
    guard = RemoteControlPlaneOperationGuard(client)  # type: ignore[arg-type]
    invokes = 0

    async def invoke() -> GraphRunSnapshot:
        nonlocal invokes
        invokes += 1
        return snapshot

    result = await guard.execute(
        organization_id=snapshot.organization_id,
        operation_id=uuid4(),
        operation_type="langgraph.start",
        request_hash="a" * 64,
        invoke=invoke,
    )

    assert result == snapshot
    assert invokes == 1
    assert client.calls[1][0].endswith("/operations/succeed")
    assert client.calls[1][1]["snapshot"] == _snapshot_payload(snapshot)


@pytest.mark.asyncio
async def test_operation_guard_replay_never_invokes_graph() -> None:
    snapshot = _snapshot()
    client = _FakeClient(
        [
            {
                "decision": "replay",
                "ledger_operation_id": str(uuid4()),
                "lease_owner": None,
                "result_json": {"schema_version": 1, "snapshot": _snapshot_payload(snapshot)},
                "error_code": None,
            }
        ]
    )
    guard = RemoteControlPlaneOperationGuard(client)  # type: ignore[arg-type]

    async def invoke() -> GraphRunSnapshot:
        raise AssertionError("replay must not invoke graph")

    result = await guard.execute(
        organization_id=snapshot.organization_id,
        operation_id=uuid4(),
        operation_type="langgraph.start",
        request_hash="b" * 64,
        invoke=invoke,
    )

    assert result == snapshot
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_unknown_execution_failure_is_marked_ambiguous() -> None:
    snapshot = _snapshot()
    client = _FakeClient(
        [
            {
                "decision": "execute",
                "ledger_operation_id": str(uuid4()),
                "lease_owner": "agent-runtime:lease",
                "result_json": {},
                "error_code": None,
            },
            {"status": "ambiguous"},
        ]
    )
    guard = RemoteControlPlaneOperationGuard(client)  # type: ignore[arg-type]

    async def invoke() -> GraphRunSnapshot:
        raise RuntimeError("transport failed after checkpoint")

    with pytest.raises(RuntimeError, match="transport failed"):
        await guard.execute(
            organization_id=snapshot.organization_id,
            operation_id=uuid4(),
            operation_type="langgraph.resume",
            request_hash="c" * 64,
            invoke=invoke,
        )

    assert client.calls[1][0].endswith("/operations/ambiguous")


@pytest.mark.asyncio
async def test_policy_denial_is_marked_final() -> None:
    snapshot = _snapshot()
    client = _FakeClient(
        [
            {
                "decision": "execute",
                "ledger_operation_id": str(uuid4()),
                "lease_owner": "agent-runtime:lease",
                "result_json": {},
                "error_code": None,
            },
            {"status": "failed_final"},
        ]
    )
    guard = RemoteControlPlaneOperationGuard(client)  # type: ignore[arg-type]

    async def invoke() -> GraphRunSnapshot:
        raise GraphResumeDeniedError("approval is pending")

    with pytest.raises(GraphResumeDeniedError):
        await guard.execute(
            organization_id=snapshot.organization_id,
            operation_id=uuid4(),
            operation_type="langgraph.resume",
            request_hash="d" * 64,
            invoke=invoke,
        )

    assert client.calls[1][0].endswith("/operations/fail-final")
    assert client.calls[1][1]["error_code"] == "GRAPH_RESUME_DENIED"


@pytest.mark.asyncio
async def test_event_retry_reuses_exact_payload() -> None:
    snapshot = _snapshot()
    client = _FakeClient(
        [
            AgentControlUnavailableError("response lost"),
            {"status": "recorded", "event_id": str(uuid4())},
        ]
    )
    sink = RemoteGraphEventSink(client)  # type: ignore[arg-type]
    event = GraphRunEvent(
        event_type="agent_run.succeeded",
        organization_id=snapshot.organization_id,
        project_id=snapshot.project_id,
        agent_run_id=snapshot.agent_run_id,
        thread_id=snapshot.thread_id,
        graph_key=snapshot.graph_key,
        graph_version=snapshot.graph_version,
        checkpoint_id=snapshot.checkpoint_id,
        occurred_at=datetime.now(UTC),
        payload={"status": "succeeded"},
        trace_id="trace-1",
    )

    await sink.publish(event)

    assert len(client.calls) == 2
    assert client.calls[0] == client.calls[1]


@pytest.mark.asyncio
async def test_approval_reader_preserves_canonical_scope() -> None:
    approval_id = uuid4()
    organization_id = uuid4()
    project_id = uuid4()
    agent_run_id = uuid4()
    client = _FakeClient(
        [
            {
                "approval_id": str(approval_id),
                "organization_id": str(organization_id),
                "project_id": str(project_id),
                "agent_run_id": str(agent_run_id),
                "status": "approved",
                "decision_payload": {"reason": "reviewed"},
            }
        ]
    )
    reader = RemoteApprovalDecisionReader(client)  # type: ignore[arg-type]

    record = await reader.get_approval(approval_id)

    assert record.approval_id == approval_id
    assert record.organization_id == organization_id
    assert record.project_id == project_id
    assert record.agent_run_id == agent_run_id
    assert record.status == "approved"
