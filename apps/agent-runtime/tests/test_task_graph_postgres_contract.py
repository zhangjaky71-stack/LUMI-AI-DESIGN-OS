from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from uuid import uuid4

from lumi_agent_runtime.task_graph import logical_operation_key

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/task_graph/postgres_store.py"
MIGRATION = ROOT / "apps/api/alembic/versions/0015_task_graph_runtime.py"


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

    def test_store_writes_existing_task_ledger_and_outbox(self) -> None:
        text = STORE.read_text(encoding="utf-8")
        self.assertIn("INSERT INTO tasks (", text)
        self.assertIn("INSERT INTO task_dependencies", text)
        self.assertIn("INSERT INTO outbox_events", text)
        self.assertNotIn("CREATE TABLE", text)

    def test_logical_operation_key_is_stable_across_attempts(self) -> None:
        graph_id = uuid4()
        task_id = uuid4()
        first = logical_operation_key(graph_id, task_id)
        second = logical_operation_key(graph_id, task_id)
        self.assertEqual(first, second)
        self.assertNotIn("attempt", first)
        self.assertEqual(first, f"task:{graph_id}:{task_id}")

    def test_migration_allows_logical_key_reuse_across_attempt_rows(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertIn('sa.Column("logical_operation_key"', text)
        self.assertIn('sa.UniqueConstraint("task_id", "attempt_number"', text)
        self.assertNotIn(
            'sa.UniqueConstraint("logical_operation_key"',
            text,
        )
        self.assertIn("ix_task_attempts_logical_operation", text)

    def test_outbox_helper_is_coroutine(self) -> None:
        from lumi_agent_runtime.task_graph import postgres_store

        self.assertTrue(inspect.iscoroutinefunction(postgres_store._insert_outbox))


if __name__ == "__main__":
    unittest.main()
