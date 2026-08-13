from __future__ import annotations

import asyncio
import os
from typing import TypedDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from lumi_agent_runtime.control_plane.checkpointing import open_postgres_checkpointer
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
from lumi_agent_runtime.control_plane.postgres_store import PostgresGraphRunStore
from lumi_agent_runtime.control_plane.registry import GraphRegistry
from lumi_agent_runtime.control_plane.testing import (
    MemoryEventSink,
    MemoryOperationGuard,
    StaticResumeAuthorizer,
)
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID

_SCHEMA = "node28_checkpoint_acceptance"


class State(TypedDict, total=False):
    brief: str
    draft: str
    approval: dict[str, str]
    finished: bool


class ConnectionFactory:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def __call__(self):
        return await asyncpg.connect(self.dsn)


def _dsn(name: str) -> str:
    return os.environ[name].replace("postgresql+asyncpg://", "postgresql://", 1)


def _with_search_path(dsn: str, schema: str) -> str:
    parsed = urlsplit(dsn)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema},public"
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def _builder(counts: dict[str, int]) -> StateGraph:
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
                "summary": "Approve restart acceptance",
                "risk": "write_external",
            }
        )
        return {"approval": dict(decision)}

    def finish_node(state: State) -> State:
        counts["finish"] += 1
        return {"finished": state.get("approval", {}).get("decision") == "approved"}

    builder = StateGraph(State)
    builder.add_node("draft", draft_node)
    builder.add_node("review", review_node)
    builder.add_node("finish", finish_node)
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "review")
    builder.add_edge("review", "finish")
    builder.add_edge("finish", END)
    return builder


def _control(
    *,
    definition: GraphDefinition,
    compiled,
    store: PostgresGraphRunStore,
) -> LangGraphControlPlane:
    graphs = DurableCompiledGraphRegistry()
    graphs.register(definition, compiled)
    return LangGraphControlPlane(
        registry=GraphRegistry((definition,)),
        executor=DurableLangGraphExecutor(graphs=graphs, bindings=store),
        store=store,
        resume_authorizer=StaticResumeAuthorizer(
            normalized_value={
                "decision": "approved",
                "approval_id": "00000000-0000-0000-0000-000000000001",
            }
        ),
        operation_guard=MemoryOperationGuard(),
        events=MemoryEventSink(),
    )


async def main_async() -> None:
    runtime_dsn = _dsn("DATABASE_URL")
    admin_dsn = _dsn("MIGRATION_DATABASE_URL")
    checkpoint_dsn = _with_search_path(admin_dsn, _SCHEMA)
    admin = await asyncpg.connect(admin_dsn)
    agent_run_id = uuid4()
    thread_id = f"node28-restart-{uuid4()}"
    counts = {"draft": 0, "review": 0, "finish": 0}
    definition = GraphDefinition(
        graph_key="acceptance.restart",
        graph_version="1.0.0",
        agent_config_version="agent-v1",
        description="NODE-28 durable PostgreSQL restart acceptance",
        state_schema_version=1,
    )
    store = PostgresGraphRunStore(ConnectionFactory(runtime_dsn))
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')
        await admin.execute(f'CREATE SCHEMA "{_SCHEMA}"')
        await admin.execute(
            """
            INSERT INTO agent_runs (
                id, organization_id, project_id, thread_id, graph_version,
                agent_config_version, status, budget, started_at, version
            ) VALUES ($1,$2,$3,$4,'1.0.0','agent-v1','pending','{}'::jsonb,now(),1)
            """,
            agent_run_id,
            ORG_ID,
            PROJECT_A_ID,
            thread_id,
        )
        request = GraphRunRequest(
            organization_id=ORG_ID,
            project_id=PROJECT_A_ID,
            agent_run_id=agent_run_id,
            operation_id=uuid4(),
            graph_key=definition.graph_key,
            graph_version=definition.graph_version,
            agent_config_version=definition.agent_config_version,
            input={"brief": "restart"},
            thread_id=thread_id,
        )

        # Deployment/admin initializes official LangGraph checkpoint tables.
        async with open_postgres_checkpointer(
            checkpoint_dsn,
            allow_setup=True,
        ) as checkpointer:
            first_graph = _builder(counts).compile(checkpointer=checkpointer)
            paused = await _control(
                definition=definition,
                compiled=first_graph,
                store=store,
            ).start(request)
            assert paused.status == GraphRunStatus.INTERRUPTED
            assert paused.checkpoint_id
            interrupt_id = paused.interrupts[0].interrupt_id
            assert counts == {"draft": 1, "review": 1, "finish": 0}, counts

        # Simulate runtime restart: old saver/compiled graph/control plane are gone. Reopen
        # the PostgreSQL saver and reconstruct the graph with the SAME immutable version.
        async with open_postgres_checkpointer(
            checkpoint_dsn,
            allow_setup=False,
        ) as checkpointer:
            restarted_graph = _builder(counts).compile(checkpointer=checkpointer)
            restarted = _control(
                definition=definition,
                compiled=restarted_graph,
                store=store,
            )
            resumed = await restarted.resume(
                ResumeRequest(
                    organization_id=ORG_ID,
                    project_id=PROJECT_A_ID,
                    agent_run_id=agent_run_id,
                    operation_id=uuid4(),
                    thread_id=thread_id,
                    interrupt_id=interrupt_id,
                    decision=ResumeDecision.APPROVED,
                    value={"decision": "forged-client-value"},
                )
            )
            assert resumed.status == GraphRunStatus.SUCCEEDED
            assert resumed.state_values["finished"] is True
            assert resumed.checkpoint_id != paused.checkpoint_id
            assert counts == {"draft": 1, "review": 2, "finish": 1}, counts
    finally:
        await admin.execute("DELETE FROM agent_run_control WHERE agent_run_id=$1", agent_run_id)
        await admin.execute("DELETE FROM agent_runs WHERE id=$1", agent_run_id)
        await admin.execute(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE')
        await admin.close()


def main() -> int:
    asyncio.run(main_async())
    print("NODE-28 PostgreSQL LangGraph restart/checkpoint integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
