from __future__ import annotations

import asyncio
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from lumi_agent_runtime.control_plane.contracts import (
    GraphDefinition,
    GraphRunRequest,
    GraphRunStatus,
    ResumeDecision,
    ResumeRequest,
)
from lumi_agent_runtime.control_plane.control_plane import LangGraphControlPlane
from lumi_agent_runtime.control_plane.durable_executor import (
    DurableCompiledGraphRegistry,
    DurableLangGraphExecutor,
)
from lumi_agent_runtime.control_plane.registry import GraphRegistry
from lumi_agent_runtime.control_plane.testing import (
    MemoryEventSink,
    MemoryGraphRunStore,
    MemoryOperationGuard,
    StaticResumeAuthorizer,
)


class State(TypedDict, total=False):
    brief: str
    draft: str
    approval: dict[str, str]
    finished: bool


async def main_async() -> None:
    counts = {"draft": 0, "review": 0, "finish": 0}

    def draft_node(state: State) -> State:
        counts["draft"] += 1
        return {"draft": f"draft:{state['brief']}"}

    def review_node(state: State) -> State:
        del state
        counts["review"] += 1
        decision = interrupt(
            {
                "kind": "approval",
                "approval_id": "00000000-0000-0000-0000-000000000001",
                "action": "publish",
                "summary": "Approve deterministic publish",
                "risk": "write_external",
            }
        )
        return {"approval": dict(decision)}

    def finish_node(state: State) -> State:
        counts["finish"] += 1
        approved = state.get("approval", {}).get("decision") == "approved"
        return {"finished": approved}

    builder = StateGraph(State)
    builder.add_node("draft", draft_node)
    builder.add_node("review", review_node)
    builder.add_node("finish", finish_node)
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "review")
    builder.add_edge("review", "finish")
    builder.add_edge("finish", END)
    compiled = builder.compile(checkpointer=InMemorySaver())

    definition = GraphDefinition(
        graph_key="acceptance.langgraph",
        graph_version="1.0.0",
        agent_config_version="agent-v1",
        description="NODE-28 current LangGraph interrupt/checkpoint acceptance",
        state_schema_version=1,
    )
    compiled_registry = DurableCompiledGraphRegistry()
    compiled_registry.register(definition, compiled)
    store = MemoryGraphRunStore()
    executor = DurableLangGraphExecutor(graphs=compiled_registry, bindings=store)
    events = MemoryEventSink()
    control = LangGraphControlPlane(
        registry=GraphRegistry((definition,)),
        executor=executor,
        store=store,
        resume_authorizer=StaticResumeAuthorizer(
            normalized_value={
                "decision": "approved",
                "approval_id": "00000000-0000-0000-0000-000000000001",
            }
        ),
        operation_guard=MemoryOperationGuard(),
        events=events,
    )

    request = GraphRunRequest(
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        graph_key=definition.graph_key,
        graph_version=definition.graph_version,
        agent_config_version=definition.agent_config_version,
        input={"brief": "launch"},
        thread_id=f"node28-{uuid4()}",
    )
    paused = await control.start(request)
    assert paused.status == GraphRunStatus.INTERRUPTED
    assert paused.checkpoint_id
    assert len(paused.interrupts) == 1
    interrupt_id = paused.interrupts[0].interrupt_id
    assert counts == {"draft": 1, "review": 1, "finish": 0}, counts

    resumed = await control.resume(
        ResumeRequest(
            organization_id=request.organization_id,
            project_id=request.project_id,
            agent_run_id=request.agent_run_id,
            operation_id=uuid4(),
            thread_id=request.thread_id,
            interrupt_id=interrupt_id,
            decision=ResumeDecision.APPROVED,
            value={"decision": "client-value-must-not-be-used"},
        )
    )
    assert resumed.status == GraphRunStatus.SUCCEEDED
    assert resumed.checkpoint_id
    assert resumed.checkpoint_id != paused.checkpoint_id
    assert resumed.state_values["finished"] is True

    # LangGraph resumes from checkpoint: the already completed draft node is not rerun.
    # The node containing interrupt() itself restarts from its beginning on resume, which
    # is why LUMI requires NODE-20 idempotency for any side effect in such a node.
    assert counts == {"draft": 1, "review": 2, "finish": 1}, counts
    assert [event.event_type for event in events.events] == [
        "agent_run.started",
        "agent_run.interrupted",
        "agent_run.resumed",
        "agent_run.succeeded",
    ]


def main() -> int:
    asyncio.run(main_async())
    print("NODE-28 current LangGraph checkpoint/interrupt integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
