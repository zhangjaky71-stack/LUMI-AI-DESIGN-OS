from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID

import lumi_api.persistence.models  # noqa: F401
from sqlalchemy import Numeric, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.config import Settings
from lumi_api.persistence.base import Base
from lumi_api.persistence.models import CostLedger, Project
from lumi_api.persistence.repositories import TenantRepository
from lumi_api.persistence.session import require_database_url

EXPECTED_TABLES = {
    "users",
    "organizations",
    "organization_members",
    "workspaces",
    "workspace_members",
    "auth_identities",
    "sessions",
    "password_credentials",
    "email_verification_tokens",
    "password_reset_tokens",
    "organization_invites",
    "api_tokens",
    "projects",
    "project_members",
    "brands",
    "brand_palettes",
    "brand_fonts",
    "brand_logos",
    "brand_rules",
    "assets",
    "asset_files",
    "asset_previews",
    "asset_metadata",
    "asset_embeddings",
    "asset_rights",
    "design_documents",
    "design_document_versions",
    "artifacts",
    "artifact_branches",
    "artifact_versions",
    "artifact_edges",
    "artifact_files",
    "artifact_provenance",
    "agent_runs",
    "agent_run_steps",
    "tasks",
    "task_dependencies",
    "approvals",
    "generations",
    "provider_requests",
    "cost_ledger",
    "usage_counters",
    "idempotency_operations",
    "outbox_events",
    "inbox_events",
    "audit_events",
}

GLOBAL_IDENTITY_TABLES = {
    "users",
    "organizations",
    "auth_identities",
    "password_credentials",
    "email_verification_tokens",
    "password_reset_tokens",
}
TENANT_TABLES = EXPECTED_TABLES - GLOBAL_IDENTITY_TABLES
IMMUTABLE_HISTORY_TABLES = {
    "design_document_versions",
    "artifact_edges",
    "artifact_files",
    "artifact_provenance",
    "cost_ledger",
    "inbox_events",
    "audit_events",
}


def test_all_current_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert len(Base.metadata.tables) == 46


def test_tenant_tables_carry_organization_id() -> None:
    for table_name in TENANT_TABLES:
        table = Base.metadata.tables[table_name]
        assert "organization_id" in table.c, table_name


def test_business_ids_have_no_database_generated_uuid_default() -> None:
    for table in Base.metadata.sorted_tables:
        if "id" not in table.c:
            continue
        id_column = table.c.id
        assert id_column.server_default is None, table.name


def test_only_recoverable_project_and_asset_use_soft_delete_in_p0() -> None:
    tables_with_deleted_at = {
        table.name for table in Base.metadata.sorted_tables if "deleted_at" in table.c
    }
    assert tables_with_deleted_at == {"projects", "assets"}


def test_immutable_history_tables_have_no_updated_at() -> None:
    for table_name in IMMUTABLE_HISTORY_TABLES:
        assert "updated_at" not in Base.metadata.tables[table_name].c


def test_cost_and_usage_precision_never_use_float() -> None:
    amount = CostLedger.__table__.c.amount.type
    quantity = CostLedger.__table__.c.quantity.type
    assert isinstance(amount, Numeric)
    assert amount.precision == 20
    assert amount.scale == 8
    assert isinstance(quantity, Numeric)
    assert quantity.precision == 30
    assert quantity.scale == 10


def test_tenant_repository_compiles_organization_predicate() -> None:
    repository = TenantRepository(
        cast(AsyncSession, object()),
        UUID("01900000-0000-7000-8000-000000000001"),
        Project,
    )
    statement = repository.scoped(select(Project))
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "projects.organization_id" in sql


def test_runtime_database_url_requires_asyncpg() -> None:
    settings = Settings(database_url="postgresql+asyncpg://user:pass@localhost/lumi")
    assert require_database_url(settings).startswith("postgresql+asyncpg://")


def test_migrations_are_frozen_and_chained_without_live_metadata_execution() -> None:
    versions = Path(__file__).parents[1] / "alembic" / "versions"
    first = (versions / "0001_domain_core_schema.py").read_text(encoding="utf-8")
    second = (versions / "0002_workflow_platform_schema.py").read_text(encoding="utf-8")
    hardening = (versions / "0003_runtime_privilege_hardening.py").read_text(encoding="utf-8")
    auth = (versions / "0004_auth_security.py").read_text(encoding="utf-8")

    for source in (first, second, hardening, auth):
        assert "Base.metadata.create_all" not in source
        assert "metadata.create_all" not in source

    assert 'down_revision = "0001_domain_core_schema"' in second
    assert 'down_revision = "0002_workflow_platform_schema"' in hardening
    assert 'down_revision = "0003_runtime_privilege_hardening"' in auth
    assert "CREATE TRIGGER trg_cost_ledger_immutable" in hardening
    assert "GRANT UPDATE (status, quality_score) ON artifact_versions" in hardening
    assert "password_credentials" in auth
    assert "api_tokens" in auth


def test_lineage_and_task_self_loop_guards_exist_in_schema() -> None:
    artifact_constraints = {
        constraint.name for constraint in Base.metadata.tables["artifact_edges"].constraints
    }
    task_constraints = {
        constraint.name for constraint in Base.metadata.tables["task_dependencies"].constraints
    }
    assert "ck_artifact_edges_artifact_edge_no_self_loop" in artifact_constraints
    assert "ck_task_dependencies_task_dependency_no_self_loop" in task_constraints


def test_auth_secrets_are_hashed_and_sessions_have_csrf_revocation_fields() -> None:
    password_columns = Base.metadata.tables["password_credentials"].c
    assert "password_hash" in password_columns
    assert "password" not in password_columns

    for table_name in (
        "email_verification_tokens",
        "password_reset_tokens",
        "organization_invites",
    ):
        columns = Base.metadata.tables[table_name].c
        assert "token_hash" in columns
        assert "token" not in columns

    api_columns = Base.metadata.tables["api_tokens"].c
    assert "secret_hash" in api_columns
    assert "secret" not in api_columns
    assert "prefix" in api_columns

    session_columns = Base.metadata.tables["sessions"].c
    for required in ("token_hash", "csrf_token_hash", "expires_at", "last_seen_at", "revoked_at"):
        assert required in session_columns
