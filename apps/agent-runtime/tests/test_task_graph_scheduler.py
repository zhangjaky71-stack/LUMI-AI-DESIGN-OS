from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import uuid4

from lumi_agent_runtime.task_graph import DurableTaskGraphScheduler
from lumi_agent_runtime.task_graph.scheduler import _row_to_task


class FakeDurableStore:
    def __init__(self, rows: tuple[dict[str, object], ...]) -> None:
        self.rows = rows
        self.ready: list[object] = []
        self.reclaimed = False
        self.claimed = False

    async def list_tasks(self, graph_id):
        return self.rows

    async def mark_ready(self, task_id, *, expected_version, expected_status, event_payload=None):
        self.ready.append(task_id)
        return {"id": task_id, "status": "READY"}

    async def reclaim_expired(self, graph_id, *, now):
        self.reclaimed = True
        return ()

    async def claim_ready(self, graph_id, *, worker_id, now, lease_seconds, limit):
        self.claimed = True
        return ({"id": self.ready[0], "status": "RUNNING"},) if self.ready else ()


def row(*, graph_id, task_id, status, depends_on=(), output=None, condition=None):
    return {
        "id": task_id,
        "task_graph_id": graph_id,
        "organization_id": uuid4(),
        "project_id": uuid4(),
        "agent_run_id": uuid4(),
        "parent_task_id": None,
        "task_key": str(task_id),
        "recipe_step_id": str(task_id),
        "type": "AGENT",
        "owner_key": "AGENT:creative-director@1.1.0",
        "status": status,
        "depends_on": depends_on,
        "input_json": {},
        "output_json": output or {},
        "metadata_json": {},
        "output_schema": "DesignOutput",
        "priority": 100,
        "attempt_count": 0,
        "max_attempts": 3,
        "budget_limit_usd": None,
        "progress_current": 0,
        "progress_total": 1,
        "dynamic_depth": 0,
        "dynamic_child_limit": 0,
        "concurrency_group": None,
        "concurrency_limit": None,
        "condition_expression": condition,
        "state_version": 1,
    }


class DurableSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_recovered_condition_promotes_pending_task_before_claim(self) -> None:
        graph_id = uuid4()
        first_id, second_id = uuid4(), uuid4()
        rows = (
            row(graph_id=graph_id, task_id=first_id, status="SUCCEEDED"),
            row(
                graph_id=graph_id,
                task_id=second_id,
                status="PENDING",
                depends_on=(first_id,),
                condition="inputs.enabled == True",
            ),
        )
        store = FakeDurableStore(rows)
        scheduler = DurableTaskGraphScheduler(store)  # type: ignore[arg-type]
        claimed = await scheduler.run_once(
            graph_id,
            worker_id="scheduler-test",
            now=datetime(2026, 8, 14, tzinfo=UTC),
            condition_context={"inputs": {"enabled": True}},
        )
        self.assertTrue(store.reclaimed)
        self.assertTrue(store.claimed)
        self.assertEqual(store.ready, [second_id])
        self.assertEqual(claimed[0]["id"], second_id)

    def test_row_recovery_preserves_condition_expression(self) -> None:
        graph_id, task_id = uuid4(), uuid4()
        task = _row_to_task(
            row(
                graph_id=graph_id,
                task_id=task_id,
                status="PENDING",
                condition="inputs.enabled == True",
            )
        )
        self.assertEqual(task.condition, "inputs.enabled == True")
        self.assertEqual(task.graph_id, graph_id)


if __name__ == "__main__":
    unittest.main()
