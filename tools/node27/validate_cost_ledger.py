from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(path: str, *needles: str) -> None:
    payload = text(path)
    for needle in needles:
        if needle not in payload:
            raise SystemExit(f"{path}: missing NODE-27 marker: {needle}")


def forbid(path: str, *needles: str) -> None:
    payload = text(path)
    for needle in needles:
        if needle in payload:
            raise SystemExit(f"{path}: forbidden NODE-27 marker: {needle}")


def validate_gateway_methods() -> None:
    path = ROOT / "apps/api/src/lumi_api/costs/gateway.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    gateway = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PostgresCostGateway"
    )
    names = [node.name for node in gateway.body if isinstance(node, ast.AsyncFunctionDef)]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise SystemExit(f"PostgresCostGateway has duplicate methods: {duplicates}")
    for required in (
        "reserve",
        "commit",
        "release",
        "record_adjustment",
        "record_reversal",
        "summary",
        "usage_summary",
        "acquire_quota_lease",
        "release_quota_lease",
    ):
        if required not in names:
            raise SystemExit(f"PostgresCostGateway missing method: {required}")


def validate_read_only_api() -> None:
    path = ROOT / "apps/api/src/lumi_api/api/v1/cost_routes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    verbs: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(
                decorator.func, ast.Attribute
            ):
                continue
            if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "router":
                verbs.append(decorator.func.attr)
    if sorted(verbs) != ["get", "get"]:
        raise SystemExit(f"NODE-27 public API must be read-only GET; found {verbs}")


def validate_gaps() -> None:
    payload = json.loads(text("reports/nodes/NODE-27/gap-ledger.json"))
    gaps = payload.get("gaps")
    if not isinstance(gaps, list) or len(gaps) != 8:
        raise SystemExit("NODE-27 gap ledger must contain exactly eight explicit gaps")
    ids = {item.get("id") for item in gaps}
    required = {
        "COST-COMPOSITION-001",
        "COST-PACKAGE-002",
        "COST-RECONCILE-003",
        "COST-UNKNOWN-004",
        "COST-BUDGET-ADMIN-005",
        "COST-QUOTA-006",
        "COST-OBS-007",
        "COST-CI-008",
    }
    if ids != required:
        raise SystemExit(f"NODE-27 gap ids mismatch: {sorted(ids)}")


def main() -> int:
    require(
        "apps/api/src/lumi_api/costs/contracts.py",
        "class CostEntryType",
        "class CostBasis",
        "class CostConfidence",
        "COST_FLOAT_FORBIDDEN",
        "UsageFact",
        "ActualCost",
        "BudgetReservationRequest",
        "CostAdjustment",
        "QuotaLease",
    )
    forbid(
        "apps/api/src/lumi_api/costs/contracts.py",
        "amount: float",
        "quantity: float",
        "estimated_amount: float",
    )
    require(
        "apps/api/migrations/versions/20260816_0009_cost_ledger.py",
        'revision = "20260816_0009"',
        'down_revision = "20260816_0008"',
        '"down_03_guard.sql"',
    )
    require(
        "apps/api/migrations/versions/20260816_0009_sql/up_01.sql",
        "uq_cost_ledger_operation_entry_key",
        "external_provider_request_id",
        "pricing_snapshot_id",
        "legacy_migration",
        "CREATE TABLE usage_ledger",
        "CREATE TABLE cost_budget_limits",
        "CREATE TABLE cost_reservations",
        "CREATE TABLE quota_limits",
        "CREATE TABLE quota_leases",
    )
    require(
        "apps/api/migrations/versions/20260816_0009_sql/up_02.sql",
        "lumi_normalize_cost_status",
        "trg_cost_ledger_immutable",
        "trg_usage_ledger_immutable",
        "tenant_isolation_usage_ledger",
        "REVOKE UPDATE, DELETE ON cost_ledger FROM lumi_app",
        "GRANT SELECT ON cost_budget_limits, quota_limits TO lumi_app",
    )
    require(
        "apps/api/migrations/versions/20260816_0009_sql/down_03_guard.sql",
        "NODE-27 downgrade refused",
        "source <> 'legacy_migration'",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/ports.py",
        "usage: ModelUsage",
        "provider_request_id: str | None",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/gateway.py",
        "usage=result.usage",
        "provider_request_id=result.provider_request_id",
    )
    require(
        "apps/api/src/lumi_api/costs/model_gateway_adapter.py",
        "class Node27BudgetPort",
        "COST_UNKNOWN_COST_HARD_BUDGET",
        "external_provider_request_id=provider_request_id",
        "class Node27CostTelemetryPort",
    )
    require(
        "apps/api/src/lumi_api/costs/read_service.py",
        "app.current_organization_id",
        "PostgresCostReadService",
    )
    require(
        "apps/api/src/lumi_api/api/v1/app.py",
        "app.include_router(cost_router, dependencies=[Depends(enforce_api_auth)])",
    )
    require(
        "apps/api/src/lumi_api/persistence/models.py",
        "models_costs as _models_costs",
    )
    require(
        "reports/nodes/NODE-27/acceptance.md",
        "IMPLEMENTED / VALIDATING",
        "not COMPLETE",
    )
    validate_gateway_methods()
    validate_read_only_api()
    validate_gaps()
    print("NODE-27 Cost Ledger architecture/financial contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
