from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/projects/v1"
SOURCE = ROOT / "services/project-core/src/lumi_project_core"
MIGRATION = ROOT / "apps/api/alembic/versions/0006_project_core.py"

EXPECTED_SCHEMA_IDS = {
    "project.schema.json": "https://schemas.lumi.dev/projects/v1/project.schema.json",
    "project-brief.schema.json": "https://schemas.lumi.dev/projects/v1/project-brief.schema.json",
    "project-settings.schema.json": "https://schemas.lumi.dev/projects/v1/project-settings.schema.json",
}
EXPECTED_BRIEF_FIELDS = {
    "schema_version",
    "objective",
    "audience",
    "brand_context",
    "deliverables",
    "channels",
    "visual_direction",
    "copy_requirements",
    "constraint_ids",
    "reference_asset_ids",
    "locale",
    "notes",
}
EXPECTED_SETTINGS_FIELDS = {
    "default_locale",
    "timezone",
    "cost_budget_default",
    "quality_profile",
    "model_policy_id",
    "data_retention_profile",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "fastapi",
    "sqlalchemy",
    "alembic",
    "langchain",
    "langgraph",
    "openai",
    "anthropic",
    "requests",
    "httpx",
)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected object: {path}")
    return value


def validate_schemas() -> None:
    for filename, expected_id in EXPECTED_SCHEMA_IDS.items():
        schema = load(CONTRACT / filename)
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        assert schema.get("$id") == expected_id
        assert schema.get("additionalProperties") is False

    project = load(CONTRACT / "project.schema.json")
    assert project["properties"]["status"]["enum"] == ["draft", "active", "paused", "archived"]
    assert project["properties"]["brief_version"]["minimum"] == 1
    assert project["properties"]["settings"]["$ref"] == "project-settings.schema.json"

    brief = load(CONTRACT / "project-brief.schema.json")
    assert set(brief["required"]) == EXPECTED_BRIEF_FIELDS
    assert set(brief["properties"]) == EXPECTED_BRIEF_FIELDS
    assert brief["properties"]["constraint_ids"]["uniqueItems"] is True
    assert brief["properties"]["reference_asset_ids"]["uniqueItems"] is True

    settings = load(CONTRACT / "project-settings.schema.json")
    assert set(settings["required"]) == EXPECTED_SETTINGS_FIELDS
    assert set(settings["properties"]) == EXPECTED_SETTINGS_FIELDS
    serialized = json.dumps(settings).lower()
    for forbidden in ("secret", "api_key", "access_key", "password"):
        assert forbidden not in serialized


def validate_dependency_boundary() -> None:
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                if name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    raise AssertionError(
                        f"Project Core contract must remain dependency-light: {name} in {path}"
                    )


def validate_migration_boundary() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0006_project_core"' in source
    assert 'down_revision = "0005_auth_role_hardening"' in source
    assert "CREATE TABLE project_brief_versions" in source
    assert "CREATE TABLE project_summaries" in source
    assert "trg_project_brief_versions_immutable" in source
    assert "BEFORE UPDATE OR DELETE ON project_brief_versions" in source
    assert "brief_version integer NOT NULL DEFAULT 1" in source
    assert "status IN ('draft','active','paused','archived')" in source
    assert "Base.metadata.create_all" not in source
    assert "presigned" not in source.lower()


def main() -> None:
    validate_schemas()
    validate_dependency_boundary()
    validate_migration_boundary()
    print("Project Core V1 contracts OK: schemas, dependency boundary and migration invariants validated")


if __name__ == "__main__":
    main()
