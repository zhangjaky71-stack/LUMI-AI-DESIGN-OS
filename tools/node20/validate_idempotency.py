from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "apps/api/src/lumi_api/idempotency"
MIGRATION = ROOT / "apps/api/migrations/versions/20260816_0006_idempotency_side_effects.py"
UP1 = ROOT / "apps/api/migrations/versions/20260816_0006_sql/up_01.sql"
UP2 = ROOT / "apps/api/migrations/versions/20260816_0006_sql/up_02.sql"
LEDGER = ROOT / "reports/nodes/NODE-20/gap-ledger.json"

FORBIDDEN_IMPORT_PREFIXES = (
    "openai",
    "anthropic",
    "boto3",
    "botocore",
    "redis",
    "langgraph",
    "langchain",
)
REQUIRED_METRICS = {
    "idempotency_replay_total",
    "idempotency_conflict_total",
    "stale_lease_total",
    "provider_reconciliation_total",
    "duplicate_prevented_total",
    "ambiguous_side_effect_total",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def validate_import_boundary() -> None:
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    fail(f"forbidden provider/agent/cache import {name} in {path}")


def validate_migration() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    if 'revision = "20260816_0006"' not in migration or 'down_revision = "20260816_0005"' not in migration:
        fail("NODE-20 Alembic chain is invalid")
    up = UP1.read_text(encoding="utf-8") + "\n" + UP2.read_text(encoding="utf-8")
    required = (
        "uq_idempotency_org_operation_key",
        "lease_owner",
        "lease_expires_at",
        "provider_request_id",
        "recovery_state",
        "uq_cost_ledger_charge_operation",
        "operation_id",
        "tenant_isolation_idempotency_operations",
    )
    missing = [marker for marker in required if marker not in up]
    if missing:
        fail(f"NODE-20 migration missing markers: {missing}")


def validate_gateway_metrics() -> None:
    gateway = (PACKAGE / "gateway.py").read_text(encoding="utf-8")
    missing = sorted(metric for metric in REQUIRED_METRICS if metric not in gateway)
    if missing:
        fail(f"gateway missing required metrics: {missing}")
    if "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST" not in gateway:
        fail("canonical same-key/different-request error code missing")


def validate_gap_ledger() -> None:
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    ids = [item["id"] for item in payload["gaps"]]
    if len(ids) != len(set(ids)):
        fail("duplicate NODE-20 gap IDs")
    if set(ids) != {
        "IDEMP-API-001",
        "IDEMP-PROVIDER-002",
        "IDEMP-RETENTION-003",
        "IDEMP-OBS-004",
        "IDEMP-CI-005",
    }:
        fail(f"unexpected NODE-20 gaps: {ids}")


def main() -> None:
    validate_import_boundary()
    validate_migration()
    validate_gateway_metrics()
    validate_gap_ledger()
    print("NODE20_IDEMPOTENCY_CONTRACT_VALID")


if __name__ == "__main__":
    main()
