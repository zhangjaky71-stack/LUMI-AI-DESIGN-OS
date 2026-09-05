from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import uuid4

from lumi_agent_runtime.control_plane.contracts import (
    CheckpointPointer,
    GraphDefinition,
    GraphInterrupt,
    GraphRunRequest,
    GraphRunStatus,
    InterruptKind,
    ResumeDecision,
    ResumeRequest,
)
from lumi_agent_runtime.control_plane.control_plane import LangGraphControlPlane
from lumi_agent_runtime.control_plane.errors import (
    GraphCheckpointConflictError,
    GraphInterruptNotFoundError,
    GraphResumeDeniedError,
    GraphRunTerminalError,
)
from lumi_agent_runtime.control_plane.registry import GraphRegistry
from lumi_agent_runtime.control_plane.testing import (
    MemoryEventSink,
    MemoryGraphRunStore,
    MemoryOperationGuard,
    ScriptedGraphExecutor,
    StaticResumeAuthorizer,
    snapshot,
)


def definition() -> GraphDefinition:
    return GraphDefinition(
        graph_key="design.plan",
        graph_version="1.0.0",
        agent_config_version="agent-v7",
        description="Deterministic design planning graph",
        state_schema_version=1,
    )


def request(defn: GraphDefinition) -> GraphRunRequest:
    return GraphRunRequest(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        operation_id=uuid4(),
        task_id=uuid4(),
        graph_key=defn.graph_key,
        graph_version=defn.graph_version,
        agent_config_version=defn.agent_config_version,
        input={"brief": "launch page"},
        thread_id=f"thread-{uuid4()}",
    )


def interrupt(interrupt_id: str = "interrupt-1") -> GraphInterrupt:
    return GraphInterrupt(
        interrupt_id=interrupt_id,
        kind=InterruptKind.APPROVAL,
        namespace=("review",),
        node_name="review",
        payload={
            "kind": "approval",
            "approval_id": str(uuid4()),
            "summary": "Approve external publish",
        },
        resumable=True,
    )


class ControlPlaneTests(unittest.IsolatedAsyncioTestCase):
    def build(
        self,
        *,
        defn: GraphDefinition,
        executor: ScriptedGraphExecutor,
        store: MemoryGraphRunStore | None = None,
        authorizer: StaticResumeAuthorizer | None = None,
    ) -> tuple[
        LangGraphControlPlane,
        MemoryGraphRunStore,
        MemoryOperationGuard,
        MemoryEventSink,
        StaticResumeAuthorizer,
    ]:
        run_store = store or MemoryGraphRunStore()
        operation_guard = MemoryOperationGuard()
        events = MemoryEventSink()
        resume_authorizer = authorizer or StaticResumeAuthorizer(
            normalized_value={"decision": "approved", "source": "lumi"}
        )
        control = LangGraphControlPlane(
            registry=GraphRegistry((defn,)),
            executor=executor,
            store=run_store,
            resume_authorizer=resume_authorizer,
            operation_guard=operation_guard,
            events=events,
        )
        return control, run_store, operation_guard, events, resume_authorizer

    async def test_duplicate_start_operation_executes_graph_once(self) -> None:
        defn = definition()
        req = request(defn)
        done = snapshot(
            definition=defn,
            request=req,
            status=GraphRunStatus.SUCCEEDED,
            checkpoint_id="cp-1",
            state_values={"result": "ok"},
        )
        executor = ScriptedGraphExecutor([done])
        control, _, guard, events, _ = self.build(defn=defn, executor=executor)

        first = await control.start(req)
        second = await control.start(req)

        self.assertEqual(first.checkpoint_id, "cp-1")
        self.assertEqual(second.checkpoint_id, "cp-1")
        self.assertEqual(executor.start_calls, 1)
        self.assertEqual(guard.invocations, 1)
        self.assertEqual(
            [event.event_type for event in events.events],
            ["agent_run.started", "agent_run.succeeded"],
        )

    async def test_resume_uses_authorized_normalized_value_not_client_value(self) -> None:
        defn = definition()
        req = request(defn)
        paused = snapshot(
            definition=defn,
            request=req,
            status=GraphRunStatus.INTERRUPTED,
            checkpoint_id="cp-1",
            interrupts=(interrupt("i-1"),),
            next_nodes=("review",),
        )
        done = snapshot(
            definition=defn,
            request=req,
            status=GraphRunStatus.SUCCEEDED,
            checkpoint_id="cp-2",
            state_values={"published": True},
        )
        executor = ScriptedGraphExecutor([paused, done])
        authorizer = StaticResumeAuthorizer(
            normalized_value={"decision": "approved", "source": "durable-approval"}
        )
        control, _, _, _, _ = self.build(
            defn=defn,
            executor=executor,
            authorizer=authorizer,
        )
        await control.start(req)
        resume = ResumeRequest(
            organization_id=req.organization_id,
            project_id=req.project_id,
            agent_run_id=req.agent_run_id,
            operation_id=uuid4(),
            thread_id=req.thread_id,
            interrupt_id="i-1",
            decision=ResumeDecision.APPROVED,
            value={"decision": "approved", "source": "client-forged"},
        )
        result = await control.resume(resume)

        self.assertEqual(result.status, GraphRunStatus.SUCCEEDED)
        self.assertEqual(executor.resume_calls, 1)
        self.assertEqual(
            executor.resume_values,
            [{"decision": "approved", "source": "durable-approval"}],
        )

    async def test_wrong_interrupt_id_never_calls_authorizer_or_executor(self) -> None:
        defn = definition()
        req = request(defn)
        paused = snapshot(
            definition=defn,
            request=req,
            status=GraphRunStatus.INTERRUPTED,
            checkpoint_id="cp-1",
            interrupts=(interrupt("expected"),),
            next_nodes=("review",),
        )
        executor = ScriptedGraphExecutor([paused])
        control, _, _, _, authorizer = self.build(defn=defn, executor=executor)
        await control.start(req)
        with self.assertRaises(GraphInterruptNotFoundError):
            await control.resume(
                ResumeRequest(
                    organization_id=req.organization_id,
                    project_id=req.project_id,
                    agent_run_id=req.agent_run_id,
                    operation_id=uuid4(),
                    thread_id=req.thread_id,
                    interrupt_id="wrong",
                    decision=ResumeDecision.APPROVED,
                    value=True,
                )
            )
        self.assertEqual(authorizer.calls, [])
        self.assertEqual(executor.resume_calls, 0)

    async def test_resume_denied_before_graph_execution(self) -> None:
        defn = definition()
        req = request(defn)
        paused = snapshot(
            definition=defn,
            request=req,
            status=GraphRunStatus.INTERRUPTED,
            checkpoint_id="cp-1",
            interrupts=(interrupt("i-1"),),
            next_nodes=("review",),
        )
        executor = ScriptedGraphExecutor([paused])
        authorizer = StaticResumeAuthorizer(authorized=False)
        control, _, _, _, _ = self.build(
            defn=defn,
            executor=executor,
            authorizer=authorizer,
        )
        await control.start(req)
        with self.assertRaises(GraphResumeDeniedError):
            await control.resume(
                ResumeRequest(
                    organization_id=req.organization_id,
                    project_id=req.project_id,
                    agent_run_id=req.agent_run_id,
                    operation_id=uuid4(),
                    thread_id=req.thread_id,
                    interrupt_id="i-1",
                    decision=ResumeDecision.APPROVED,
                    value=True,
                )
            )
        self.assertEqual(executor.resume_calls, 0)

    async def test_terminal_run_cannot_resume(self) -> None:
        defn = definition()
        req = request(defn)
        done = snapshot(
            definition=defn,
            request=req,
            status=GraphRunStatus.SUCCEEDED,
            checkpoint_id="cp-final",
        )
        executor = ScriptedGraphExecutor([done])
        control, _, _, _, _ = self.build(defn=defn, executor=executor)
        await control.start(req)
        with self.assertRaises(GraphRunTerminalError):
            await control.resume(
                ResumeRequest(
                    organization_id=req.organization_id,
                    project_id=req.project_id,
                    agent_run_id=req.agent_run_id,
                    operation_id=uuid4(),
                    thread_id=req.thread_id,
                    interrupt_id="unused",
                    decision=ResumeDecision.APPROVED,
                    value=True,
                )
            )

    async def test_store_checkpoint_compare_and_swap_rejects_stale_persist(self) -> None:
        defn = definition()
        req = request(defn)
        store = MemoryGraphRunStore()
        self.assertIsNone(await store.bind_start(req, defn))
        cp1 = snapshot(
            definition=defn,
            request=req,
            status=GraphRunStatus.INTERRUPTED,
            checkpoint_id="cp-1",
            interrupts=(interrupt("i-1"),),
            next_nodes=("review",),
        )
        await store.persist_snapshot(cp1, expected_checkpoint=None)
        cp2 = snapshot(
            definition=defn,
            request=req,
            status=GraphRunStatus.SUCCEEDED,
            checkpoint_id="cp-2",
        )
        with self.assertRaises(GraphCheckpointConflictError):
            await store.persist_snapshot(
                cp2,
                expected_checkpoint=CheckpointPointer(
                    thread_id=req.thread_id,
                    checkpoint_namespace="",
                    checkpoint_id="stale",
                ),
            )

    def test_snapshot_contract_rejects_nonfinite_state(self) -> None:
        defn = definition()
        req = request(defn)
        with self.assertRaisesRegex(ValueError, "GRAPH_NON_FINITE_NUMBER"):
            from lumi_agent_runtime.control_plane.contracts import GraphRunSnapshot

            GraphRunSnapshot(
                organization_id=req.organization_id,
                project_id=req.project_id,
                agent_run_id=req.agent_run_id,
                task_id=req.task_id,
                thread_id=req.thread_id,
                graph_key=defn.graph_key,
                graph_version=defn.graph_version,
                agent_config_version=defn.agent_config_version,
                status=GraphRunStatus.RUNNING,
                checkpoint_id="cp",
                checkpoint_namespace="",
                state_values={"bad": float("nan")},
                next_nodes=("node",),
                interrupts=(),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )


if __name__ == "__main__":
    unittest.main()
