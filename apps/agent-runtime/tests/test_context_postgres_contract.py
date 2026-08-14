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
            return {
                child.target.id
                for child in node.body
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
            }
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

    def test_project_task_asset_queries_are_tenant_scoped(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("organization_id", text)
        self.assertIn("project_id", text)
        self.assertIn("WHERE id = $1 AND organization_id = $2", text)
        self.assertIn("a.organization_id = $1 AND a.project_id = $2", text)
        self.assertIn("WHERE organization_id = $1 AND project_id = $2", text)

    def test_adapter_reads_canonical_project_brand_task_asset_artifact_sources(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        for marker in (
            "FROM projects",
            "brief_json",
            "brief_version",
            "profile_json",
            "tone_json",
            "brand_rules",
            "FROM tasks",
            "task_dependencies",
            "FROM assets",
            "asset_metadata",
            "FROM artifacts",
            "asset_embeddings",
        ):
            self.assertIn(marker, text)
        for forbidden in ("project_summaries", "summary/source_digest", "chat_history", "conversation_messages", "raw_chat"):
            self.assertNotIn(forbidden, text)

    def test_embedding_query_uses_actual_asset_embedding_model_fields(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        fields = class_fields(ASSET_MODEL, "AssetEmbedding")
        self.assertIn("embedding", fields)
        self.assertIn("dimensions", fields)
        self.assertIn("e.embedding", text)
        self.assertIn("e.dimensions", text)
        self.assertIn("query_embedding", text)
        self.assertNotIn("e.dims", text)

    def test_project_contract_matches_model(self) -> None:
        fields = class_fields(PROJECT_MODEL, "Project")
        for field in ("organization_id", "brief_json", "brief_version", "settings_json", "brand_id", "deleted_at"):
            self.assertIn(field, fields)

    def test_asset_contract_matches_model(self) -> None:
        fields = class_fields(ASSET_MODEL, "Asset")
        for field in ("organization_id", "project_id", "original_name", "metadata_json", "status", "deleted_at"):
            self.assertIn(field, fields)


if __name__ == "__main__":
    unittest.main()
