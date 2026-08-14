from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "apps/api/alembic/versions/0017_knowledge_engine.py"
ORM = ROOT / "apps/api/src/lumi_api/persistence/models/knowledge.py"
REPOSITORY = (
    ROOT
    / "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/postgres_repository.py"
)
RETRIEVAL = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/retrieval.py"
CONTEXT_CONTRACT = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/context_engine/contracts.py"


class KnowledgePostgresContractTests(unittest.TestCase):
    def test_migration_stacks_on_memory_and_has_versioned_index_identity(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertIn('down_revision = "0016_memory_engine"', text)
        self.assertIn("CREATE TABLE knowledge_documents", text)
        self.assertIn("CREATE TABLE knowledge_chunks", text)
        self.assertIn("permission_scope", text)
        self.assertIn("scope_key", text)
        self.assertIn("parser_version", text)
        self.assertIn("chunker_version", text)
        self.assertIn("index_version", text)
        self.assertIn("embedding_space_id", text)
        self.assertIn("source_updated_at", text)
        self.assertIn("search_tsv tsvector GENERATED ALWAYS AS", text)
        self.assertIn("USING gin (search_tsv)", text)
        self.assertIn("REVOKE DELETE", text)
        self.assertIn("scope_key='PROJECT:' || project_id::text", text)
        self.assertIn("scope_key='ORGANIZATION'", text)
        for state in (
            "PENDING",
            "EXTRACTING",
            "CHUNKING",
            "EMBEDDING",
            "READY",
            "FAILED",
            "STALE",
            "SUPERSEDED",
            "DELETED",
        ):
            self.assertIn(state, text)

    def test_orm_matches_migration_identity(self) -> None:
        text = ORM.read_text(encoding="utf-8")
        self.assertIn('__tablename__ = "knowledge_documents"', text)
        self.assertIn('__tablename__ = "knowledge_chunks"', text)
        self.assertIn("permission_scope", text)
        self.assertIn("scope_key", text)
        self.assertIn("index_version", text)
        self.assertIn("embedding_space_id", text)
        self.assertIn("source_updated_at", text)
        self.assertIn("Computed(\"to_tsvector('simple', text)\"", text)
        self.assertIn('"ix_knowledge_chunks_fts"', text)
        self.assertIn('postgresql_using="gin"', text)

    def test_postgres_repository_is_sdk_neutral_and_transaction_safe(self) -> None:
        text = REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("pg_advisory_xact_lock", text)
        self.assertIn("scope_key", text)
        self.assertIn("FOR UPDATE", text)
        self.assertIn("version=version+1", text)
        self.assertIn("ON CONFLICT (document_id, ordinal) DO UPDATE", text)
        tree = ast.parse(text)
        forbidden = {
            "asyncpg",
            "sqlalchemy",
            "psycopg",
            "openai",
            "anthropic",
            "google",
        }
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        self.assertFalse(imported & forbidden)

    def test_project_acl_is_in_durable_fts_and_vector_candidate_queries(self) -> None:
        postgres = REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("d.project_id=$2", postgres)
        self.assertIn("d.permission_scope='ORGANIZATION'", postgres)
        self.assertIn("websearch_to_tsquery", postgres)
        self.assertIn("c.search_tsv", postgres)
        self.assertIn("c.embedding <=> $4::vector", postgres)
        self.assertIn("c.embedding_space_id=$5", postgres)
        retrieval = RETRIEVAL.read_text(encoding="utf-8")
        self.assertIn("search_ready_chunks", retrieval)
        self.assertLess(
            retrieval.index("search_ready_chunks"),
            retrieval.index("score = min"),
        )

    def test_context_contract_exposes_knowledge_evidence_kind(self) -> None:
        text = CONTEXT_CONTRACT.read_text(encoding="utf-8")
        self.assertIn('KNOWLEDGE = "KNOWLEDGE"', text)


if __name__ == "__main__":
    unittest.main()
