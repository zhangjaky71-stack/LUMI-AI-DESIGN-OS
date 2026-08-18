from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(haystack: str, needle: str, label: str) -> None:
    if needle not in haystack:
        raise SystemExit(f"NODE63_VALIDATION_FAILED:{label}:{needle}")


def forbid(haystack: str, needle: str, label: str) -> None:
    if needle in haystack:
        raise SystemExit(f"NODE63_VALIDATION_FAILED:{label}:{needle}")


def main() -> None:
    migration = read("apps/api/migrations/versions/20260818_0023_sql/up.sql")
    migration_py = read("apps/api/migrations/versions/20260818_0023_billing.py")
    repo = read("apps/api/src/lumi_api/billing/repository.py")
    safe_repo = read("apps/api/src/lumi_api/billing/repository_safe.py")
    service = read("apps/api/src/lumi_api/billing/service.py")
    provider = read("apps/api/src/lumi_api/billing/provider.py")
    reconciliation = read("apps/api/src/lumi_api/billing/reconciliation.py")
    app = read("apps/api/src/lumi_api/api/v1/app.py")
    routes = read("apps/api/src/lumi_api/api/v1/billing_routes.py")
    policy = read("apps/api/src/lumi_api/auth/policy.py")
    web_types = read("apps/web/src/lib/billing/types.ts")
    web_page = read("apps/web/src/app/(shell)/settings/billing/page.tsx")
    web_portal = read("apps/web/src/components/billing/billing-portal-button.tsx")

    require(migration_py, 'down_revision = "20260818_0022"', "linear migration")
    for table in (
        "billing_plans",
        "billing_plan_versions",
        "billing_accounts",
        "billing_subscriptions",
        "billing_credit_wallets",
        "billing_credit_ledger",
        "billing_invoice_refs",
        "billing_payment_events",
    ):
        require(migration, f"CREATE TABLE {table}", f"table {table}")

    require(migration, "trg_billing_credit_ledger_immutable", "credit immutable trigger")
    require(migration, "trg_billing_plan_version_material_immutable", "plan version guard")
    require(repo, "FOR UPDATE", "credit concurrency fence")
    require(repo, "BILLING_INSUFFICIENT_CREDITS", "no negative surprise")
    require(safe_repo, "ON CONFLICT (provider, provider_event_id) DO NOTHING", "safe duplicate claim")
    forbid(safe_repo, "IntegrityError", "duplicate exception control flow")
    require(safe_repo, "BILLING_PAYMENT_EVENT_BODY_CONFLICT", "webhook body conflict fence")
    require(service, '"billing.read"', "billing read permission")
    require(service, '"billing.manage"', "billing manage permission")
    require(service, "pricing_policy", "versioned usage pricing")
    forbid(service.casefold(), "plan ==", "plan-name entitlement branching")
    require(provider, "hmac.compare_digest", "constant-time webhook verification")
    require(provider, '"card_number"', "card-data rejection")
    require(provider, '"cvc"', "card-data rejection")
    require(reconciliation, "FROM cost_ledger", "provider cost read projection")
    forbid(reconciliation, "UPDATE cost_ledger", "cost ledger mutation")
    forbid(reconciliation, "INSERT INTO cost_ledger", "cost ledger mutation")
    forbid(repo, "UPDATE cost_ledger", "cost ledger mutation")
    forbid(repo, "INSERT INTO cost_ledger", "cost ledger mutation")
    require(app, "app.include_router(billing_webhook_router)", "public signed webhook route")
    require(
        app,
        "app.include_router(billing_router, dependencies=[Depends(enforce_api_auth)])",
        "authenticated billing product route",
    )
    require(routes, 'Header(alias="X-Lumi-Mock-Signature")', "mock webhook signature")
    require(policy, 'BILLING_READ = "billing.read"', "billing read RBAC")
    require(policy, 'BILLING_MANAGE = "billing.manage"', "billing manage RBAC")
    require(web_types, "BILLING_PORTAL_URL_UNSAFE", "hosted portal parser guard")
    require(web_page, 'session.permissions.includes("billing.read")', "web read projection")
    require(web_page, 'session.permissions.includes("billing.manage")', "web manage projection")
    require(web_portal, 'window.location.assign(portal.url)', "hosted portal navigation")
    print("NODE63_BILLING_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
