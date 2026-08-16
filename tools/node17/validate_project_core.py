from __future__ import annotations

import ast
import re
from pathlib import Path

from lumi_api.projects import ProjectBrief, ProjectEventType, ProjectSettings

ROOT = Path(__file__).resolve().parents[2]
PROJECT_DIR = ROOT / "apps" / "api" / "src" / "lumi_api" / "projects"
MIGRATION = ROOT / "apps" / "api" / "migrations" / "versions" / "20260816_0003_project_core.py"
SQL_DIR = ROOT / "apps" / "api" / "migrations" / "versions" / "20260816_0003_sql"
ROUTES = ROOT / "apps" / "api" / "src" / "lumi_api" / "api" / "v1" / "routes.py"
DOMAIN_REPOS = ROOT / "apps" / "api" / "src" / "lumi_api" / "domain" / "repositories.py"

FORBIDDEN_PROJECT_IMPORTS = {
    "openai",
    "anthropic",
    "langchain",
    "langgraph",
    "boto3",
    "PIL",
    "cv2",
}


def assert_structured_contracts() -> None:
    brief_fields = set(ProjectBrief.model_fields)
    expected = {
        "objective",
        "audience",
        "brand_context",
        "deliverables",
        "channels",
        "visual_direction",
        "copy_requirements",
        "constraints",
        "references",
        "locale",
        "notes",
    }
    assert expected <= brief_fields
    settings_fields = set(ProjectSettings.model_fields)
    for field in (
        "default_locale",
        "timezone",
        "cost_budget_default",
        "quality_profile",
        "model_policy_id",
        "data_retention_profile",
    ):
        assert field in settings_fields
    assert {item.value for item in ProjectEventType} == {
        "project.created",
        "project.updated",
        "project.paused",
        "project.archived",
        "project.restored",
        "project.brief.updated",
    }


def assert_architecture_boundaries() -> None:
    for path in PROJECT_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    assert module not in FORBIDDEN_PROJECT_IMPORTS, (path, module)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[0]
                assert module not in FORBIDDEN_PROJECT_IMPORTS, (path, module)


def assert_migration_contract() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260816_0003"' in source
    assert 'down_revision = "20260816_0002"' in source
    assert '"up_01.sql", "up_02.sql", "up_03.sql", "up_04.sql"' in source
    snapshot = "\n".join(
        (SQL_DIR / name).read_text(encoding="utf-8")
        for name in ("up_01.sql", "up_02.sql", "up_03.sql", "up_04.sql")
    )
    for fragment in (
        "project_brief_versions",
        "project_branch_defaults",
        "project_summaries",
        "agent_run_project_context",
        "tenant_isolation_project_brief_versions",
        "tenant_isolation_project_summaries",
        "lumi_require_project_accepts_paid_command",
        "lumi_project_core_same_tenant_guard",
        "project_brief_version",
        "REVOKE UPDATE, DELETE ON TABLE project_brief_versions",
        "SET id = project_id",
    ):
        assert fragment in snapshot, fragment
    assert len(re.findall(r"ENABLE ROW LEVEL SECURITY", snapshot)) >= 4


def assert_api_contract() -> None:
    routes = ROUTES.read_text(encoding="utf-8")
    for fragment in (
        '"/projects/{project_id}/brief/versions"',
        '"/projects/{project_id}/restore"',
        "async def archive_project(",
        "project_status:",
        "updated_from:",
        "name_query:",
    ):
        assert fragment in routes, fragment


def assert_domain_repository_tenant_scope_survives() -> None:
    source = DOMAIN_REPOS.read_text(encoding="utf-8")
    get_signatures = re.findall(r"async def get\(([^)]*)\)", source)
    assert get_signatures
    for signature in get_signatures:
        assert "organization_id" in signature, signature


def main() -> None:
    assert_structured_contracts()
    assert_architecture_boundaries()
    assert_migration_contract()
    assert_api_contract()
    assert_domain_repository_tenant_scope_survives()
    print(
        "NODE17_PROJECT_CORE_VALIDATION_PASS: structured brief/settings, lifecycle, "
        "tenant repository scope, 0003 migration, RLS/same-tenant guards, paid-command guard"
    )


if __name__ == "__main__":
    main()
