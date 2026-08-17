from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from lumi_agent_runtime.task_graph import (
    ControlPlaneTaskGraphAdapter,
    FailureMode,
    InMemoryTaskGraphStore,
    JoinPolicy,
    RetryPolicy,
    TaskDefinition,
    TaskGraphConflictError,
    TaskGraphDefinition,
    TaskGraphLeaseError,
    TaskGraphScheduler,
    TaskGraphState,
    TaskKind,
    TaskState,
)
from lumi_agent_runtime.task_graph.contracts import TaskGraphEvent

NOW = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)
ORG = UUID("11111111-1111-1111-1111-111111111111")
PROJECT = UUID("22222222-2222-2222-2222-222222222222")
RUN = UUID("33333333-3333-3333-3333-333333333333")


def task(
    key: str,
    *,
    kind: TaskKind = TaskKind.DETERMINISTIC,
    depends_on: tuple[str, ...] = (),
    priority: int = 100,
    retry: RetryPolicy | None = None,
    budget: str | None = None,
    group: str | None = None,
    group_limit: int | None = None,
    join: JoinPolicy = JoinPolicy.ALL_SUCCESS,
) -> TaskDefinition:
    kwargs = {}
    if kind is TaskKind.AGENTIC:
        kwargs = {
            "agent_ref": "designer@1.2.3",
            "context_bundle_ref": f"context-bundle://{ORG}/{PROJECT}/" + "a" * 64,
        }
    return TaskDefinition(
        task_key=key,
        kind=kind,
        objective=f"execute {key}",
        depends_on=depends_on,
        priority=priority,
        retry=retry or RetryPolicy(),
        budget_limit_usd=budget,
        concurrency_group=group,
        concurrency_limit=group_limit,
        join_policy=join,
        **kwargs,
    )


def graph_def(
    tasks: tuple[TaskDefinition, ...],
    *,
    run: UUID = RUN,
    budget: str = "10",
    max_parallelism: int = 4,
    failure_mode: FailureMode = FailureMode.FAIL_FAST,
) -> TaskGraphDefinition:
    return TaskGraphDefinition(
        graph_key="lumi.task_graph",
        exact_version="1.0.0",
        organization_id=ORG,
        project_id=PROJECT,
        agent_run_id=run,
        tasks=tasks,
        budget_limit_usd=budget,
        max_parallelism=max_parallelism,
        failure_mode=failure_mode,
        provenance_refs=("git://lumi/node33",),
    )


@pytest.mark.asyncio
async def test_dag_and_exact_agent_contracts() -> None:
    with pytest.raises(ValueError, match="TASK_GRAPH_CYCLE"):
        graph_def((task("a", depends_on=("b",)), task("b", depends_on=("a",))))
    with pytest.raises(ValueError, match="TASK_AGENT_EXACT_REF_REQUIRED"):
        TaskDefinition(task_key="agent", kind=TaskKind.AGENTIC, objective="x")
    definition = graph_def((task("agent", kind=TaskKind.AGENTIC),))
    assert len(definition.definition_hash) == 64
    assert definition.graph_id == graph_def((task("agent", kind=TaskKind.AGENTIC),)).graph_id


@pytest.mark.asyncio
async def test_idempotent_instantiation_and_definition_conflict() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    definition = graph_def((task("a"),))
    first = await scheduler.ensure_graph(definition, now=NOW)
    second = await scheduler.ensure_graph(definition, now=NOW + timedelta(seconds=1))
    assert first.graph_id == second.graph_id
    changed = replace(definition, tasks=(task("a"), task("b")))
    with pytest.raises(TaskGraphConflictError, match="TASK_GRAPH_RUN_DEFINITION_CONFLICT"):
        await scheduler.ensure_graph(changed, now=NOW)


@pytest.mark.asyncio
async def test_dependency_promotion_and_completion() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    graph = await scheduler.ensure_graph(
        graph_def((task("a"), task("b", depends_on=("a",)))), now=NOW
    )
    tasks = await scheduler.tasks(graph.graph_id)
    assert [item.status for item in tasks] == [TaskState.READY, TaskState.PENDING]
    lease = (await scheduler.claim_ready(graph.graph_id, worker_id="worker-1", now=NOW))[0]
    await scheduler.complete(
        graph.graph_id,
        lease.task.task_id,
        worker_id="worker-1",
        lease_token=lease.lease_token,
        now=NOW + timedelta(seconds=1),
        result_ref="artifact://a/result",
    )
    await scheduler.refresh_ready(graph.graph_id, now=NOW + timedelta(seconds=2))
    tasks = await scheduler.tasks(graph.graph_id)
    assert [item.status for item in tasks] == [TaskState.SUCCEEDED, TaskState.READY]


@pytest.mark.asyncio
async def test_priority_parallelism_and_concurrency_group() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    definition = graph_def(
        (
            task("low", priority=1),
            task("high", priority=500, group="gpu", group_limit=1),
            task("high2", priority=400, group="gpu", group_limit=1),
        ),
        max_parallelism=2,
    )
    graph = await scheduler.ensure_graph(definition, now=NOW)
    leases = await scheduler.claim_ready(
        graph.graph_id, worker_id="worker-1", now=NOW, limit=3
    )
    assert [lease.task.task_key for lease in leases] == ["high", "low"]


@pytest.mark.asyncio
async def test_retry_backoff_preserves_logical_operation_key() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    retry = RetryPolicy(max_attempts=3, base_delay_seconds=10, max_delay_seconds=30)
    graph = await scheduler.ensure_graph(graph_def((task("a", retry=retry),)), now=NOW)
    first = (await scheduler.claim_ready(graph.graph_id, worker_id="worker-1", now=NOW))[0]
    failed = await scheduler.fail(
        graph.graph_id,
        first.task.task_id,
        worker_id="worker-1",
        lease_token=first.lease_token,
        now=NOW + timedelta(seconds=1),
        retryable=True,
        error_code="PROVIDER_TRANSIENT",
    )
    assert failed.status is TaskState.FAILED_RETRYABLE
    assert failed.retry_not_before == NOW + timedelta(seconds=11)
    assert await scheduler.claim_ready(
        graph.graph_id, worker_id="worker-2", now=NOW + timedelta(seconds=5)
    ) == ()
    second = (
        await scheduler.claim_ready(
            graph.graph_id, worker_id="worker-2", now=NOW + timedelta(seconds=11)
        )
    )[0]
    assert first.logical_operation_key == second.logical_operation_key
    assert first.lease_token != second.lease_token
    assert second.task.attempt_count == 2


@pytest.mark.asyncio
async def test_lease_fencing_heartbeat_and_reclaim() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    graph = await scheduler.ensure_graph(graph_def((task("a"),)), now=NOW)
    lease = (
        await scheduler.claim_ready(
            graph.graph_id, worker_id="worker-1", now=NOW, lease_seconds=5
        )
    )[0]
    with pytest.raises(TaskGraphLeaseError, match="TASK_LEASE_FENCING_MISMATCH"):
        await scheduler.heartbeat(
            lease.task.task_id,
            graph_id=graph.graph_id,
            worker_id="worker-1",
            lease_token="stale-token",
            now=NOW + timedelta(seconds=1),
        )
    hb = await scheduler.heartbeat(
        lease.task.task_id,
        graph_id=graph.graph_id,
        worker_id="worker-1",
        lease_token=lease.lease_token,
        now=NOW + timedelta(seconds=1),
        lease_seconds=5,
    )
    assert hb.lease_expires_at == NOW + timedelta(seconds=6)
    reclaimed = await scheduler.reclaim_expired(
        graph.graph_id, now=NOW + timedelta(seconds=7)
    )
    assert reclaimed == (lease.task.task_id,)
    task_after = (await scheduler.tasks(graph.graph_id))[0]
    assert task_after.status is TaskState.FAILED_RETRYABLE
    events = await store.events(graph.graph_id)
    assert any(
        event.event_type == "task.lease_expired"
        and event.payload["provider_reconciliation_required"] is True
        for event in events
    )


@pytest.mark.asyncio
async def test_fail_fast_skips_unstarted_and_drains_running() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    graph = await scheduler.ensure_graph(
        graph_def((task("a"), task("b"), task("c", depends_on=("a",)))), now=NOW
    )
    leases = await scheduler.claim_ready(
        graph.graph_id, worker_id="worker-1", now=NOW, limit=2
    )
    by_key = {lease.task.task_key: lease for lease in leases}
    await scheduler.fail(
        graph.graph_id,
        by_key["a"].task.task_id,
        worker_id="worker-1",
        lease_token=by_key["a"].lease_token,
        now=NOW + timedelta(seconds=1),
        retryable=False,
        error_code="HARD_FAIL",
    )
    snapshot = await scheduler.graph(graph.graph_id)
    assert snapshot.status is TaskGraphState.FAILURE_DRAINING
    tasks = {item.task_key: item for item in await scheduler.tasks(graph.graph_id)}
    assert tasks["c"].status is TaskState.SKIPPED
    assert tasks["b"].cancellation_requested_at is not None
    await scheduler.complete(
        graph.graph_id,
        tasks["b"].task_id,
        worker_id="worker-1",
        lease_token=by_key["b"].lease_token,
        now=NOW + timedelta(seconds=2),
    )
    assert (await scheduler.graph(graph.graph_id)).status is TaskGraphState.FAILED_FINAL


@pytest.mark.asyncio
async def test_continue_mode_keeps_independent_work_and_skips_failed_join() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    graph = await scheduler.ensure_graph(
        graph_def(
            (task("a"), task("b"), task("c", depends_on=("a",))),
            failure_mode=FailureMode.CONTINUE,
        ),
        now=NOW,
    )
    leases = await scheduler.claim_ready(
        graph.graph_id, worker_id="worker-1", now=NOW, limit=2
    )
    by_key = {lease.task.task_key: lease for lease in leases}
    await scheduler.fail(
        graph.graph_id,
        by_key["a"].task.task_id,
        worker_id="worker-1",
        lease_token=by_key["a"].lease_token,
        now=NOW + timedelta(seconds=1),
        retryable=False,
        error_code="FINAL",
    )
    await scheduler.refresh_ready(graph.graph_id, now=NOW + timedelta(seconds=2))
    tasks = {item.task_key: item for item in await scheduler.tasks(graph.graph_id)}
    assert tasks["c"].status is TaskState.SKIPPED
    assert tasks["b"].status is TaskState.RUNNING
    await scheduler.complete(
        graph.graph_id,
        tasks["b"].task_id,
        worker_id="worker-1",
        lease_token=by_key["b"].lease_token,
        now=NOW + timedelta(seconds=3),
    )
    assert (await scheduler.graph(graph.graph_id)).status is TaskGraphState.FAILED_FINAL


@pytest.mark.asyncio
async def test_budget_gate_blocks_new_claims_but_keeps_recorded_cost() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    graph = await scheduler.ensure_graph(
        graph_def((task("a"), task("b")), budget="1", max_parallelism=1), now=NOW
    )
    first = (await scheduler.claim_ready(graph.graph_id, worker_id="worker-1", now=NOW))[0]
    await scheduler.complete(
        graph.graph_id,
        first.task.task_id,
        worker_id="worker-1",
        lease_token=first.lease_token,
        now=NOW + timedelta(seconds=1),
        cost_amount_usd="1",
    )
    snapshot = await scheduler.graph(graph.graph_id)
    assert snapshot.cost_spent_usd == "1.000000"
    assert snapshot.status is TaskGraphState.FAILED_FINAL
    assert snapshot.error_code == "TASK_GRAPH_BUDGET_EXHAUSTED"
    assert await scheduler.claim_ready(
        graph.graph_id, worker_id="worker-2", now=NOW + timedelta(seconds=2)
    ) == ()


@pytest.mark.asyncio
async def test_pause_resume_and_cancel_drain() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    graph = await scheduler.ensure_graph(graph_def((task("a"), task("b"))), now=NOW)
    paused = await scheduler.pause(graph.graph_id, now=NOW + timedelta(seconds=1))
    assert paused.status is TaskGraphState.PAUSED
    assert await scheduler.claim_ready(
        graph.graph_id, worker_id="worker-1", now=NOW + timedelta(seconds=2)
    ) == ()
    resumed = await scheduler.resume(
        graph.graph_id, now=NOW + timedelta(seconds=3)
    )
    assert resumed.status is TaskGraphState.RUNNING
    lease = (
        await scheduler.claim_ready(
            graph.graph_id, worker_id="worker-1", now=NOW + timedelta(seconds=4), limit=1
        )
    )[0]
    cancelled = await scheduler.cancel(graph.graph_id, now=NOW + timedelta(seconds=5))
    assert cancelled.status is TaskGraphState.CANCEL_REQUESTED
    tasks = {item.task_key: item for item in await scheduler.tasks(graph.graph_id)}
    running_key = lease.task.task_key
    other_key = "b" if running_key == "a" else "a"
    assert tasks[running_key].cancellation_requested_at is not None
    assert tasks[other_key].status is TaskState.CANCELLED
    await scheduler.complete(
        graph.graph_id,
        lease.task.task_id,
        worker_id="worker-1",
        lease_token=lease.lease_token,
        now=NOW + timedelta(seconds=6),
    )
    assert (await scheduler.graph(graph.graph_id)).status is TaskGraphState.CANCELLED


@pytest.mark.asyncio
async def test_wait_suspend_and_resolution() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    graph = await scheduler.ensure_graph(
        graph_def((task("approval", kind=TaskKind.APPROVAL),)), now=NOW
    )
    lease = (
        await scheduler.claim_ready(
            graph.graph_id, worker_id="worker-1", now=NOW, limit=1
        )
    )[0]
    waiting = await scheduler.suspend(
        graph.graph_id,
        lease.task.task_id,
        worker_id="worker-1",
        lease_token=lease.lease_token,
        now=NOW + timedelta(seconds=1),
        wait_ref="approval://req/123",
        waiting_state=TaskState.WAITING_USER,
    )
    assert waiting.status is TaskState.WAITING_USER
    assert (await scheduler.graph(graph.graph_id)).status is TaskGraphState.WAITING
    resolved = await scheduler.resolve_wait(
        graph.graph_id,
        waiting.task_id,
        now=NOW + timedelta(seconds=2),
        succeeded=True,
        result_ref="approval://req/123/result",
    )
    assert resolved.status is TaskState.SUCCEEDED
    assert (await scheduler.graph(graph.graph_id)).status is TaskGraphState.SUCCEEDED


class _Resolver:
    def __init__(self, definition: TaskGraphDefinition) -> None:
        self.definition = definition

    async def resolve(self, state):
        return self.definition


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


@pytest.mark.asyncio
async def test_control_plane_adapter_routes_without_hidden_claim() -> None:
    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    definition = graph_def((task("agent", kind=TaskKind.AGENTIC),))
    adapter = ControlPlaneTaskGraphAdapter(
        scheduler=scheduler,
        store=store,
        definitions=_Resolver(definition),
        clock=_Clock(NOW),
    )
    state = {
        "organization_id": str(ORG),
        "project_id": str(PROJECT),
        "run_id": str(RUN),
    }
    task_ids = await adapter.ensure_task_graph(state)
    assert len(task_ids) == 1
    assert await adapter.next_route(state) == "agentic"
    current = (await scheduler.tasks(definition.graph_id))[0]
    assert current.status is TaskState.READY
    assert current.lease_token is None


def test_safe_event_rejects_private_reasoning() -> None:
    with pytest.raises(ValueError, match="TASK_EVENT_PRIVATE_REASONING_FORBIDDEN"):
        TaskGraphEvent(
            event_type="task.progress",
            graph_id=uuid4(),
            organization_id=ORG,
            project_id=PROJECT,
            agent_run_id=RUN,
            payload={"reasoning": "secret"},
        )

@pytest.mark.asyncio
async def test_node29_scheduled_request_resolver_uses_claimed_exact_pins() -> None:
    from lumi_agent_runtime.deep_runtime.contracts import (
        DeepAgentInvocationContext,
        PermissionScope,
    )
    from lumi_agent_runtime.task_graph.deep_agent import ScheduledAgentTaskRequestResolver

    class Policy:
        async def invocation_for(self, *, task, state):
            return DeepAgentInvocationContext(
                organization_id=task.organization_id,
                project_id=task.project_id,
                agent_run_id=task.agent_run_id,
                task_id=task.task_id,
                operation_id=uuid4(),
                actor_id="actor-1",
                root_agent="designer",
                permissions=PermissionScope(allowed_tools=()),
                budget_limit_usd="1",
            )

    store = InMemoryTaskGraphStore()
    scheduler = TaskGraphScheduler(store)
    definition = graph_def((task("agent", kind=TaskKind.AGENTIC),))
    graph = await scheduler.ensure_graph(definition, now=NOW)
    lease = (
        await scheduler.claim_ready(
            graph.graph_id, worker_id="worker-1", now=NOW, limit=1
        )
    )[0]
    resolver = ScheduledAgentTaskRequestResolver(store=store, policy=Policy())
    request = await resolver.resolve(
        {
            "organization_id": str(ORG),
            "project_id": str(PROJECT),
            "run_id": str(RUN),
            "current_task_ids": [str(lease.task.task_id)],
        }
    )
    assert request.agent_ref == "designer@1.2.3"
    assert request.context_bundle_ref == lease.task.context_bundle_ref
    assert request.invocation.task_id == lease.task.task_id
