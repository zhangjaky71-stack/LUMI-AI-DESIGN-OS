# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import Float, Numeric, create_mock_engine

from lumi_api.persistence import models as _models
from lumi_api.persistence.base import Base

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = (
    ROOT
    / "apps"
    / "api"
    / "migrations"
    / "versions"
    / "20260816_0001_sql"
)
REVISION = (
    ROOT
    / "apps"
    / "api"
    / "migrations"
    / "versions"
    / "20260816_0001_p0_schema.py"
)

EXPECTED_TABLES = {
    "agent_run_steps",
    "agent_runs",
    "approvals",
    "artifact_branches",
    "artifact_edges",
    "artifact_files",
    "artifact_provenance",
    "artifact_versions",
    "artifacts",
    "asset_embeddings",
    "asset_files",
    "asset_metadata",
    "asset_previews",
    "asset_rights",
    "assets",
    "audit_events",
    "auth_identities",
    "brand_fonts",
    "brand_logos",
    "brand_palettes",
    "brand_rules",
    "brands",
    "cost_ledger",
    "design_document_versions",
    "design_documents",
    "generations",
    "idempotency_operations",
    "inbox_events",
    "organization_members",
    "organizations",
    "outbox_events",
    "project_members",
    "projects",
    "provider_requests",
    "task_dependencies",
    "tasks",
    "usage_counters",
    "users",
    "workspace_members",
    "workspaces",
}
NON_TENANT_TABLES = {"users", "organizations", "auth_identities"}
TENANT_TABLES = EXPECTED_TABLES - NON_TENANT_TABLES

# Module import is intentionally retained for metadata registration.
_METADATA_REGISTRY = _models


def load_snapshot() -> str:
    parts = [SQL_DIR / f"up_{index:02d}.sql" for index in range(1, 9)]
    missing = [str(path) for path in parts if not path.exists()]
    if missing:
        raise AssertionError(f"missing schema snapshot parts: {missing}")
    return "\n".join(path.read_text(encoding="utf-8") for path in parts)


def assert_metadata_contract() -> None:
    tables = Base.metadata.tables
    assert set(tables) == EXPECTED_TABLES

    for table_name in TENANT_TABLES:
        column = tables[table_name].columns.get("organization_id")
        assert column is not None, f"{table_name} must carry organization_id"
        assert not column.nullable, f"{table_name}.organization_id must be NOT NULL"

    for table in tables.values():
        for column in table.columns:
            assert not isinstance(column.type, Float), (
                f"floating-point persistence is forbidden: {table.name}.{column.name}"
            )

    assert isinstance(tables["cost_ledger"].columns["amount"].type, Numeric)
    assert isinstance(tables["cost_ledger"].columns["quantity"].type, Numeric)
    assert isinstance(tables["agent_runs"].columns["budget_amount"].type, Numeric)
    assert isinstance(tables["tasks"].columns["budget_reserved"].type, Numeric)

    emitted: list[str] = []
    engine = create_mock_engine("postgresql://", lambda sql, *_args, **_kwargs: emitted.append(str(sql)))
    Base.metadata.create_all(engine)
    assert emitted, "SQLAlchemy metadata must compile for PostgreSQL"


def assert_frozen_snapshot_contract(snapshot: str) -> None:
    created = set(re.findall(r"(?im)^CREATE TABLE ([a-z0-9_]+)\s*\(", snapshot))
    assert created == EXPECTED_TABLES

    assert len(re.findall(r"(?im)^ALTER TABLE .* ENABLE ROW LEVEL SECURITY;", snapshot)) == len(
        TENANT_TABLES
    )
    assert len(re.findall(r"(?im)^CREATE POLICY tenant_isolation_", snapshot)) == len(
        TENANT_TABLES
    )

    upper = snapshot.upper()
    assert " DOUBLE PRECISION" not in upper
    assert re.search(r"\bFLOAT\b", upper) is None
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in snapshot
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto;" in snapshot
    assert "embedding vector NOT NULL" in snapshot

    required_fragments = (
        "trg_cost_ledger_immutable",
        "trg_artifact_versions_history",
        "trg_task_dependencies_no_cycle",
        "trg_artifact_edges_no_cycle",
        "lumi_enforce_same_tenant_fk",
        "uq_idempotency_org_key",
        "outbox_events",
        "inbox_events",
        "ck_projects_version_positive",
        "lumi_current_organization_id",
    )
    for fragment in required_fragments:
        assert fragment in snapshot, f"missing schema safeguard: {fragment}"


def assert_revision_is_frozen() -> None:
    source = REVISION.read_text(encoding="utf-8")
    assert "20260816_0001_sql" in source
    assert "persistence.models" not in source
    assert "Base.metadata" not in source
    assert "exec_driver_sql" in source


def main() -> None:
    assert_metadata_contract()
    snapshot = load_snapshot()
    assert_frozen_snapshot_contract(snapshot)
    assert_revision_is_frozen()
    print(
        "NODE-10 schema validation PASS: "
        f"{len(EXPECTED_TABLES)} tables, {len(TENANT_TABLES)} tenant tables, "
        "exact money, frozen migration, RLS, DAG/lineage, immutability, outbox/idempotency"
    )


if __name__ == "__main__":
    main()
