from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from uuid import uuid4

from lumi_agent_runtime.task_graph import logical_operation_key

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/task_graph/postgres_store.py"
MIGRATION = ROOT / "apps/api/alembic/versions/0015_task_graph_runtime.py"
WORKFLOW_ORM = ROOT / "apps/api/src/lumi_api/persistence/models/workflow.py"
GRAPH_ORM = ROOT / "apps/api/src/lumi_api/persistence/models/task_graph.py"
MODEL_REGISTRY = ROOT / "apps/api/src/lumi_api/persistence/models/__init__.py"


class TaskGraphPostgresContractTests(unittest.TestCase):
    def test_runtime_store_has_no_database_sdk_import(self) -> None:
        text = STORE.read_text(encoding="utf-8")
        for forbidden in (
            "import asyncpg",
            "import sqlalchemy",
            "from sqlalchemy",
            "import psycopg",
        ):
            self.assertNotIn(forbidden, text)

    def test_claim_is_skip_locked_and_cas_guarded(self) -> None:
        text = STORE.read_text(encoding="utf-8")
        self.assertIn("FOR UPDATE SKIP LOCKED", text)
        self.assertIn("LIMIT 1", text)
        self.assertIn("AND state_version = $6", text)
        self.assertIn("AND status = 'READY'", text)
        self.assertIn("state_version = state_version + 1", text)
        self.assertIn("t.cancellation_requested_at IS NULL", text)
        self.assertIn("g.cancellation_requested_at IS NULL", text)

    def test_store_uses_canonical_existing_task_columns(self) -> None:
        text = STORE.read_text(encoding="utf-8")
        self.assertIn("INSERT INTO tasks (", text)
        for marker in (
            "task_key, type, status, owner_agent_key, owner_key",
            "input_json, output_json",
            "budget_reserved, budget_limit_usd",
            "output_schema, metadata_json",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("task_key, kind", text)
        self.assertNotIn("owner_agent,", text)
        self.assertNotIn("event_type", text)
        self.assertNotIn("occurred_at", text)
        self.assertNotIn("CREATE TABLE", text)

    def test_dependency_insert_supplies_legacy_required_identity(self) -> None:
        text = STORE.read_text(encoding="utf-8")
        self.assertIn(
            "id, organization_id, task_id, depends_on_task_id",
            text,
        )
        self.assertIn("uuid4()", text)
        self.assertIn("ON CONFLICT (task_id, depends_on_task_id) DO NOTHING", text)

    def test_outbox_uses_node19_canonical_columns(self) -> None:
        text = STORE.read_text(encoding="utf-8")
        self.assertIn("INSERT INTO outbox_events", text)
        self.assertIn("event_name, aggregate_type", text)
        self.assertIn("aggregate_id, schema_version, payload_json, publish_attempts", text)
        self.assertNotIn("event_type", text)

    def test_store_exposes_restart_and_timeline_primitives(self) -> None:
        text = STORE.read_text(encoding="utf-8")
        for marker in (
            "async def load_graph",
            "async def list_tasks",
            "async def list_attempts",
            "async def timeline",
            "async def heartbeat",
            "async def mark_ready",
            "async def finish_running",
            "async def resume_waiting",
            "async def schedule_retry",
            "async def reclaim_expired",
            "async def request_cancel",
        ):
            self.assertIn(marker, text)

    def test_attempt_rows_only_finish_from_running(self) -> None:
        text = STORE.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("AND status = 'RUNNING'"), 4)
        self.assertIn("TASK_ATTEMPT_FINISH_CONFLICT", text)
        self.assertIn("TASK_ATTEMPT_RECLAIM_CONFLICT", text)

    def test_logical_operation_key_is_stable_across_attempts(self) -> None:
        graph_id = uuid4()
        task_id = uuid4()
        first = logical_operation_key(graph_id, task_id)
        second = logical_operation_key(graph_id, task_id)
        self.assertEqual(first, second)
        self.assertNotIn("attempt", first)
        self.assertEqual(first, f"task:{graph_id}:{task_id}")

    def test_migration_extends_existing_task_ledger_and_attempt_lifecycle(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertIn('down_revision = "0014_agent_registry_provenance"', text)
        self.assertNotIn('op.create_table(\n        "tasks"', text)
        for marker in (
            'sa.Column("task_graph_id"',
            'sa.Column("owner_key"',
            'sa.Column("budget_limit_usd"',
            'sa.Column("output_schema"',
            'sa.Column("metadata_json"',
            'sa.Column("cancellation_requested_at"',
            'sa.Column("logical_operation_key"',
            'sa.UniqueConstraint("task_id", "attempt_number"',
            '"ix_tasks_ready_claim"',
            '"ix_tasks_lease_reap"',
            '"ix_tasks_concurrency_group"',
        ):
            self.assertIn(marker, text)
        self.assertNotIn('sa.UniqueConstraint("logical_operation_key"', text)
        self.assertIn('REVOKE DELETE ON task_attempts FROM lumi_app', text)
        self.assertIn('GRANT SELECT, INSERT, UPDATE ON task_attempts TO lumi_app', text)

    def test_sqlalchemy_metadata_knows_node33_tables_and_task_columns(self) -> None:
        workflow = WORKFLOW_ORM.read_text(encoding="utf-8")
        graph_orm = GRAPH_ORM.read_text(encoding="utf-8")
        registry = MODEL_REGISTRY.read_text(encoding="utf-8")
        for marker in (
            "task_graph_id:",
            "owner_key:",
            "budget_limit_usd:",
            "output_schema:",
            "metadata_json:",
            "cancellation_requested_at:",
            "lease_expires_at:",
            "concurrency_limit:",
        ):
            self.assertIn(marker, workflow)
        self.assertIn("class TaskGraphInstance", graph_orm)
        self.assertIn("class TaskAttemptRecord", graph_orm)
        self.assertIn("from .task_graph import TaskAttemptRecord, TaskGraphInstance", registry)
        self.assertIn('"TaskAttemptRecord"', registry)
        self.assertIn('"TaskGraphInstance"', registry)

    def test_outbox_helper_is_coroutine(self) -> None:
        from lumi_agent_runtime.task_graph import postgres_store

        self.assertTrue(inspect.iscoroutinefunction(postgres_store._insert_outbox))


if __name__ == "__main__":
    unittest.main()
