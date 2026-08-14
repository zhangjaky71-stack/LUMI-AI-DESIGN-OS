from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/context_engine/postgres_source.py"
ASSET_MODEL = ROOT / "apps/api/src/lumi_api/persistence/models/asset.py"
PROJECT_MODEL = ROOT / "apps/api/src/lumi_api/persistence/models/project.py"


def class_fields(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields: set[str] = set()
            for child in node.body:
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                    fields.add(child.target.id)
            return fields
    raise AssertionError(f"class not found: {class_name}")


class ContextPostgresContractTests(unittest.TestCase):
    def test_context_adapter_is_sdk_neutral_and_read_only(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        for forbidden in (
            "import asyncpg",
            "import sqlalchemy",
            "from sqlalchemy",
            "import psycopg",
            "INSERT INTO",
            "UPDATE ",
            "DELETE FROM",
            "openai",
            "anthropic",
        ):
            self.assertNotIn(forbidden, text)

    def test_project_and_task_queries_are_tenant_scoped(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        for marker in (
            "organization_id = $1 AND project_id = $2",
            "p.id = $1 AND p.organization_id = $2",
            "id = $1 AND organization_id = $2 AND project_id = $3",
            "a.organization_id = $1 AND a.project_id = $2",
        ):
            self.assertIn(marker, text)

    def test_adapter_reads_summaries_assets_artifacts_and_task_graph(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        for marker in (
            "FROM project_summaries",
            "JOIN brand_rules",
            "FROM tasks",
            "FROM task_dependencies",
            "FROM assets",
            "FROM artifacts",
            "FROM asset_embeddings",
        ):
            self.assertIn(marker, text)
        for forbidden in ("chat_history", "conversation_messages", "raw_chat", "messages table"):
            self.assertNotIn(forbidden, text)

    def test_embedding_query_uses_actual_asset_embedding_model_fields(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        fields = class_fields(ASSET_MODEL, "AssetEmbedding")
        self.assertIn("embedding", fields)
        self.assertIn("dims", fields)
        self.assertIn("e.embedding", text)
        self.assertIn("e.dims", text)
        self.assertIn("query_embedding", text)

    def test_project_summary_contract_matches_model(self) -> None:
        fields = class_fields(PROJECT_MODEL, "ProjectSummary")
        for field in ("organization_id", "project_id", "summary", "source_digest", "version"):
            self.assertIn(field, fields)


if __name__ == "__main__":
    unittest.main()
