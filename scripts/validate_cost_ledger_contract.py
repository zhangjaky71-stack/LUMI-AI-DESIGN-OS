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


def assert_hosted_budget_guard_not_injectable(source: str) -> None:
    tree = ast.parse(source, filename="apps/api/src/lumi_api/model_gateway_runtime.py")
    factory = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_hosted_model_gateway"
        ),
        None,
    )
    if factory is None:
        raise SystemExit("hosted Model Gateway composition function missing")
    parameter_names = {
        argument.arg
        for argument in [
            *factory.args.posonlyargs,
            *factory.args.args,
            *factory.args.kwonlyargs,
        ]
    }
    if factory.args.vararg is not None:
        parameter_names.add(factory.args.vararg.arg)
    if factory.args.kwarg is not None:
        parameter_names.add(factory.args.kwarg.arg)
    if "budget_guard" in parameter_names:
        raise SystemExit("hosted Model Gateway must not accept an injectable budget guard")


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
        "REVOKE UPDATE, DELETE ON usage_ledger FROM lumi_app",
        "REVOKE DELETE ON cost_reservations FROM lumi_app",
        "REVOKE INSERT, UPDATE, DELETE ON cost_budget_limits FROM lumi_app",
        "REVOKE INSERT, UPDATE, DELETE ON quota_limits FROM lumi_app",
        "REVOKE DELETE ON quota_leases FROM lumi_app",
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

    platform_migration = "apps/api/alembic/versions/0018_platform_provider_cost_guard.py"
    require(
        platform_migration,
        'down_revision = "0017_knowledge_engine"',
        "CREATE TABLE platform_provider_cost_guard",
        "100.00000000",
        "daily_cap_usd > 0 AND daily_cap_usd <= 100.00000000",
        "fail_closed boolean NOT NULL DEFAULT true",
        "CONSTRAINT pk_platform_provider_cost_guard PRIMARY KEY (policy_key)",
        "REVOKE INSERT, UPDATE, DELETE ON platform_provider_cost_guard FROM lumi_app",
        "GRANT SELECT ON platform_provider_cost_guard TO lumi_app",
    )

    require(
        "apps/api/src/lumi_api/persistence/models/platform_cost_guard.py",
        "class PlatformProviderCostGuard",
        '__tablename__ = "platform_provider_cost_guard"',
        "Numeric(20, 8)",
        "daily_cap_usd > 0 AND daily_cap_usd <= 100.00000000",
        "fail_closed",
    )
    require(
        "apps/api/src/lumi_api/persistence/models/__init__.py",
        "from .platform_cost_guard import PlatformProviderCostGuard",
        '"PlatformProviderCostGuard"',
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
        "apps/api/src/lumi_api/costs/platform_guard.py",
        "class PlatformGuardedCostGateway",
        "class PlatformProviderCostGuardUnavailable",
        "pg_advisory_xact_lock",
        "cost-budget:platform:provider-usd:utc-day",
        "FROM platform_provider_cost_guard",
        "FROM cost_ledger",
        "FROM cost_reservations",
        "cost_basis='provider_cost'",
        "entry_type IN ('actual_cost','adjustment','reversal')",
        "spent + active + projected_amount > cap",
        "super().reserve(request)",
        "super().commit(handle, actual)",
        "super().release(handle, reason=reason)",
    )

    require(
        "apps/api/src/lumi_api/costs/model_gateway_adapter.py",
        "class PostgresModelCostAccounting",
        "PlatformGuardedCostGateway",
        "self.gateway = PlatformGuardedCostGateway(dsn)",
        "reserve_provider_cost",
        "commit_provider_cost",
        "release_provider_cost",
        "external_provider_request_id=provider_request_id",
        '"platform_guard": "utc_day"',
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

    hosted = require(
        "apps/api/src/lumi_api/model_gateway_runtime.py",
        "def build_hosted_model_gateway",
        "PostgresModelCostAccounting(database_dsn)",
        "LedgerBudgetGuard(accounting)",
        "budget_guard=budget_guard",
        "hosted Model Gateway requires LUMI_DATABASE_URL for durable accounting",
    )
    assert_hosted_budget_guard_not_injectable(hosted)
    require(
        "apps/api/pyproject.toml",
        '"lumi-model-gateway"',
    )
    require(
        "pyproject.toml",
        "lumi-model-gateway = { workspace = true }",
    )

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
    require(
        "scripts/integration_platform_provider_cost_guard.py",
        "asyncio.gather",
        "len(handles) == 3",
        "PlatformGuardedCostGateway",
        "MAX_PLATFORM_DAILY_CAP",
        "database constraint must reject provider cap above $100",
        "baseline_spent",
        "baseline_active",
        "disabled platform provider guard must fail closed",
        "post-overshoot provider reservation must be denied",
        "runtime must not mutate platform provider cost policy",
        "platform provider USD/day hard-stop PostgreSQL acceptance: PASS",
    )
    require(
        "scripts/integration_cost_privileges.py",
        "UPDATE usage_ledger SET quantity=quantity WHERE false",
        "DELETE FROM cost_reservations WHERE false",
        "INSERT INTO cost_budget_limits",
        "UPDATE quota_limits SET quantity_limit=quantity_limit WHERE false",
        "DELETE FROM quota_leases WHERE false",
        "runtime mutation must be denied",
    )

    print("NODE-27 cost ledger/budget/quota static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
