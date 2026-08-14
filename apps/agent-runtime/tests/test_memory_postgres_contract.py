from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "apps/api/alembic/versions/0016_memory_engine.py"
ORM = ROOT / "apps/api/src/lumi_api/persistence/models/memory.py"
REPOSITORY = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/postgres_repository.py"
PIPELINE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/pipeline.py"


class MemoryPostgresContractTests(unittest.TestCase):
    def test_migration_is_stacked_on_task_graph_and_has_two_memory_tables(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertIn('down_revision = "0015_task_graph_runtime"', text)
        self.assertIn("CREATE TABLE memory_records", text)
        self.assertIn("CREATE TABLE memory_candidates", text)
        for scope in ("SESSION", "USER", "PROJECT", "BRAND", "AGENT", "ORGANIZATION"):
            self.assertIn(scope, text)
        self.assertIn("embedding vector", text)
        self.assertIn("REVOKE DELETE ON memory_records, memory_candidates FROM lumi_app", text)

    def test_orm_matches_migration_identity(self) -> None:
        text = ORM.read_text(encoding="utf-8")
        self.assertIn('__tablename__ = "memory_records"', text)
        self.assertIn('__tablename__ = "memory_candidates"', text)
        self.assertIn("embedding_dimensions", text)
        self.assertIn("retention_hold", text)
        self.assertIn("supersedes_id", text)
        self.assertIn("source_refs", text)

    def test_postgres_repository_is_sdk_neutral_and_serializes_concurrency(self) -> None:
        text = REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("pg_advisory_xact_lock", text)
        self.assertIn("FOR UPDATE", text)
        self.assertIn("version=version+1", text)
        self.assertIn("MEMORY_REJECTED_CONTENT_MUST_NOT_PERSIST", text)
        tree = ast.parse(text)
        forbidden = {"asyncpg", "sqlalchemy", "psycopg", "openai", "anthropic"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertFalse(imported & forbidden)

    def test_sensitive_and_cross_scope_rejections_do_not_persist_candidate_content(self) -> None:
        text = PIPELINE.read_text(encoding="utf-8")
        sensitive_block = text.split("if sensitivity.classification.value != \"NONE\":", 1)[1].split("policy =", 1)[0]
        self.assertNotIn("insert_candidate", sensitive_block)
        policy_block = text.split("if not policy.allowed:", 1)[1].split("if policy.outcome", 1)[0]
        self.assertNotIn("insert_candidate", policy_block)


if __name__ == "__main__":
    unittest.main()
