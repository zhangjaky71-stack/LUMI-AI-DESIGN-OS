from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from lumi_agent_runtime.task_graph import DurableTaskGraphScheduler, logical_operation_key

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/task_graph"
STORE = (PACKAGE / "postgres_store.py").read_text(encoding="utf-8")
SCHEDULER = (PACKAGE / "scheduler.py").read_text(encoding="utf-8")
MIGRATION = (ROOT / "apps/api/alembic/versions/0015_task_graph_runtime.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / "apps/api/src/lumi_api/persistence/models/workflow.py").read_text(encoding="utf-8")


class TaskGraphPostgresContractTests(unittest.TestCase):
    def test_claim_and_schema_contract(self) -> None:
        for marker in (
            "FOR UPDATE SKIP LOCKED",
            "AND state_version = $6",
            "g.status = 'RUNNING'",
            "owner_agent_key, owner_key",
            "condition_expression",
            "event_name, aggregate_type",
            "id, organization_id, task_id, depends_on_task_id",
        ):
            self.assertIn(marker, STORE)
        for forbidden in ("task_key, kind", "owner_agent,", "event_type"):
            self.assertNotIn(forbidden, STORE)

    def test_retry_identity_is_stable(self) -> None:
        graph_id, task_id = uuid4(), uuid4()
        value = logical_operation_key(graph_id, task_id)
        self.assertEqual(value, f"task:{graph_id}:{task_id}")
        self.assertNotIn("attempt", value)
        self.assertNotIn('sa.UniqueConstraint("logical_operation_key"', MIGRATION)

    def test_condition_and_runtime_fields_are_durable(self) -> None:
        for marker in (
            'sa.Column("condition_expression"',
            'sa.Column("cancellation_requested_at"',
            'sa.Column("logical_operation_key"',
            'sa.UniqueConstraint("task_id", "attempt_number"',
        ):
            self.assertIn(marker, MIGRATION)
        for marker in (
            "condition_expression:",
            "cancellation_requested_at:",
            "lease_expires_at:",
            "concurrency_limit:",
        ):
            self.assertIn(marker, WORKFLOW)
        self.assertIn("task.condition", STORE)
        self.assertIn("async def add_dynamic_task", STORE)
        self.assertIn("provider_reconciliation_required", STORE)

    def test_durable_scheduler_reuses_readiness_rules(self) -> None:
        self.assertTrue(isinstance(DurableTaskGraphScheduler, type))
        for marker in (
            "_join_decision",
            "_condition_context",
            "evaluate_expression",
            "await self.store.mark_ready",
            "await self.store.claim_ready",
            "await self.store.reclaim_expired",
        ):
            self.assertIn(marker, SCHEDULER)

    def test_attempt_history_cannot_be_deleted(self) -> None:
        self.assertIn("REVOKE DELETE ON task_attempts FROM lumi_app", MIGRATION)
        self.assertIn("GRANT SELECT, INSERT, UPDATE ON task_attempts TO lumi_app", MIGRATION)
        self.assertIn("TASK_ATTEMPT_FINISH_CONFLICT", STORE)
        self.assertIn("TASK_ATTEMPT_RECLAIM_CONFLICT", STORE)


if __name__ == "__main__":
    unittest.main()
