from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from integration_recipe_engine import build_compiler

from lumi_agent_runtime.task_graph import (
    InMemoryTaskGraphStore,
    TaskGraphState,
    TaskState,
    claim_ready_tasks,
    complete_task,
    instantiate_compiled_recipe,
    resume_waiting_task,
    wait_task,
)


def main() -> int:
    compiler = build_compiler()
    compiled = compiler.compile("product-visuals@production")
    bundle = instantiate_compiled_recipe(
        compiled,
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
    )
    assert bundle.graph.provenance.recipe_id == "product-visuals"
    assert bundle.graph.provenance.recipe_version == "1.0.0"
    assert (
        bundle.graph.provenance.recipe_definition_hash
        == compiled.definition.content_hash
    )
    assert (
        bundle.graph.provenance.recipe_provenance_hash
        == compiled.provenance.freeze_hash
    )
    assert (
        bundle.graph.provenance.task_graph_template_hash
        == compiled.task_graph.content_hash
    )

    store = InMemoryTaskGraphStore()
    store.install(bundle)
    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    max_parallel_seen = 0
    approval_waited = False
    guard = 0
    while store.graph(bundle.graph.graph_id).status not in {
        TaskGraphState.SUCCEEDED,
        TaskGraphState.FAILED_FINAL,
        TaskGraphState.CANCELLED,
    }:
        guard += 1
        if guard > 50:
            raise AssertionError("NODE-33 integration exceeded bounded scheduler guard")
        ready = claim_ready_tasks(
            store,
            bundle.graph.graph_id,
            worker_id="node33-integration-worker",
            now=now,
            limit=8,
        )
        running_parallel = [
            task
            for task in store.tasks(bundle.graph.graph_id)
            if task.status == TaskState.RUNNING
            and task.concurrency_group == "renders"
        ]
        max_parallel_seen = max(max_parallel_seen, len(running_parallel))
        if not ready:
            waiting = [
                task
                for task in store.tasks(bundle.graph.graph_id)
                if task.status == TaskState.WAITING_APPROVAL
            ]
            if waiting:
                approval_waited = True
                resume_waiting_task(
                    store,
                    waiting[0].task_id,
                    now=now,
                    resume_ref="approval://node33/approved",
                )
                continue
            raise AssertionError("NODE-33 integration stalled without ready/waiting task")
        for task in ready:
            if task.step_type == "APPROVAL" and not approval_waited:
                wait_task(
                    store,
                    task.task_id,
                    worker_id="node33-integration-worker",
                    now=now,
                    target=TaskState.WAITING_APPROVAL,
                    reason="human_review",
                    external_ref="approval://node33",
                )
                continue
            complete_task(
                store,
                task.task_id,
                worker_id="node33-integration-worker",
                now=now,
                output={
                    "task_key": task.task_key,
                    "score": 95,
                    "artifact_ref": f"artifact://node33/{task.task_key}",
                },
            )

    graph = store.graph(bundle.graph.graph_id)
    assert graph.status == TaskGraphState.SUCCEEDED
    assert graph.progress == 1.0
    assert approval_waited is True
    assert max_parallel_seen == 3
    attempts = [
        attempt
        for task in store.tasks(bundle.graph.graph_id)
        for attempt in store.attempts(task.task_id)
    ]
    assert attempts
    assert all(attempt.logical_operation_key.startswith("task:") for attempt in attempts)
    events = store.events()
    assert any(event.event_name == "task.waiting" for event in events)
    assert any(event.event_name == "task_graph.completed" for event in events)
    print("NODE-32 Recipe -> NODE-33 Task Graph integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
