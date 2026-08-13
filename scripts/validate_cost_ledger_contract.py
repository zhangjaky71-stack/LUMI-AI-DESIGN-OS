from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-27 contract marker: {needle}")
    return text


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden NODE-27 contract marker: {needle}")


def assert_model_gateway_cost_port_has_no_db_sdk() -> None:
    path = ROOT / "services/model-gateway/src/lumi_model_gateway/cost_accounting.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_roots = {"asyncpg", "sqlalchemy", "psycopg"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
            if roots & forbidden_roots:
                raise SystemExit("Model Gateway CostAccountingPort imports a DB SDK")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] in forbidden_roots:
                raise SystemExit("Model Gateway CostAccountingPort imports a DB SDK")


def main() -> int:
    migration = "apps/api/alembic/versions/0011_cost_ledger_budget_quota.py"
    require(
        migration,
        'down_revision = "0010_capability_registry"',
        "ADD COLUMN entry_key",
        "pricing_snapshot_id",
        "external_provider_request_id",
        "cost_basis",
        "provider_cost",
        "customer_charge",
        "uq_cost_ledger_operation_entry_key",
        "CREATE TABLE cost_budget_limits",
        "CREATE TABLE cost_reservations",
        "CREATE TABLE usage_ledger",
        "CREATE TABLE quota_limits",
        "CREATE TABLE quota_leases",
        "numeric(20,8)",
        "numeric(30,10)",
        "REVOKE UPDATE, DELETE ON cost_ledger FROM lumi_app",
        "GRANT SELECT, INSERT ON usage_ledger TO lumi_app",
        "GRANT SELECT, INSERT, UPDATE ON cost_reservations TO lumi_app",
        "GRANT SELECT ON cost_budget_limits, quota_limits TO lumi_app",
        "GRANT SELECT, INSERT, UPDATE ON quota_leases TO lumi_app",
    )
    forbid(
        migration,
        "GRANT SELECT, INSERT, UPDATE ON cost_budget_limits",
        "GRANT SELECT, INSERT, UPDATE ON quota_limits",
    )

    require(
        "apps/api/src/lumi_api/costs/contracts.py",
        "class ActualCost",
        "class CostAdjustment",
        "class BudgetReservationRequest",
        "class QuotaLease",
        "COST_FLOAT_FORBIDDEN",
        "Decimal",
        'PROVIDER_COST = "provider_cost"',
        'CUSTOMER_CHARGE = "customer_charge"',
        'EXACT = "exact"',
        'ESTIMATED = "estimated"',
        'UNKNOWN = "unknown"',
    )
    gateway = require(
        "apps/api/src/lumi_api/costs/gateway.py",
        "pg_advisory_xact_lock",
        "cost-budget:",
        "quota:",
        "actual cost",
        "status='committed'",
        "ON CONFLICT ON CONSTRAINT uq_cost_ledger_operation_entry_key DO NOTHING",
        "ON CONFLICT ON CONSTRAINT uq_usage_ledger_operation_metric_key DO NOTHING",
        "entry_type IN ('actual_cost','adjustment','reversal')",
        "cost_basis='provider_cost'",
        "released not-accepted reservation cannot commit",
        "reservation[\"status\"] not in {\"active\", \"expired\"}",
    )
    if "SELECT * FROM cost_budget_limits" not in gateway:
        raise SystemExit("budget policy lookup missing")
    if "ORDER BY scope_type, period_key, id\n            FOR UPDATE" in gateway:
        raise SystemExit("runtime must not require UPDATE privilege on budget policy")
    if "metric=$2 AND period_key=$3 AND enabled\n                    FOR SHARE" in gateway:
        raise SystemExit("runtime must not row-lock read-only quota policy")
    if "SELECT * FROM cost_ledger WHERE id=$1 FOR SHARE" in gateway:
        raise SystemExit("append-only ledger replay must require SELECT only")

    require(
        "apps/api/src/lumi_api/costs/model_gateway_adapter.py",
        "class PostgresModelCostAccounting",
        "reserve_provider_cost",
        "commit_provider_cost",
        "release_provider_cost",
        "external_provider_request_id=provider_request_id",
    )
    model_port = require(
        "services/model-gateway/src/lumi_model_gateway/cost_accounting.py",
        "class CostAccountingPort",
        "class LedgerBudgetGuard",
        "durable budget reservation requires an estimated provider cost",
        "commit_provider_cost",
        "release_provider_cost",
        "provider_request_id",
        "agent_run_id",
        "generation_id",
    )
    assert_model_gateway_cost_port_has_no_db_sdk()
    if "budget_limit_usd" not in model_port:
        raise SystemExit("request hard budget preflight missing from LedgerBudgetGuard")

    require(
        "services/model-gateway/src/lumi_model_gateway/gateway.py",
        "usage=result.usage",
        "provider_request_id=result.provider_request_id",
        'reason="provider_not_accepted"',
        'reason="stream_not_accepted"',
        "await reservation.commit(candidate.estimate)",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/models.py",
        "agent_run_id: UUID | None = None",
        "generation_id: UUID | None = None",
        "MODEL_COST_FLOAT_FORBIDDEN",
        "MODEL_USAGE_NEGATIVE",
    )

    require(
        "apps/api/src/lumi_api/api/v1/cost_router.py",
        '"/usage"',
        '"/costs/summary"',
        '"/projects/{project_id}/costs"',
        "get_request_context",
        "COST_TIME_RANGE_INVALID",
    )
    require(
        "apps/api/src/lumi_api/api/v1/contracts.py",
        "class CostSummaryResource",
        "class UsageSummaryResource",
        "net_provider_cost: Decimal",
    )

    require(
        "scripts/integration_cost_ledger.py",
        "asyncio.gather",
        "len(handles) == 6",
        "post-overshoot reservation must be denied",
        "replay_actual.inserted is False",
        "provider invoice reconciliation",
        "concurrent generation quota must reject third lease",
        "runtime mutation must be denied",
        "mock-price-v1",
    )

    print("NODE-27 cost ledger/budget/quota static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
