from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "services/project-core/src/lumi_project_core/billing.py",
    "services/project-core/tests/test_billing.py",
    "apps/api/src/lumi_api/billing_router.py",
    "apps/api/tests/test_billing_router.py",
    "db/migrations/0013_billing.sql",
    "apps/web/src/app/app/billing/page.tsx",
    "apps/web/src/components/billing/billing-center.tsx",
    "apps/web/src/lib/billing/billing-gateway.ts",
    "apps/web/src/lib/billing/billing-server.ts",
    "apps/web/e2e/billing.spec.ts",
    "docs/runtime/BILLING-V1.md",
    "reports/nodes/NODE-63/acceptance.md",
]
for relative in REQUIRED:
    if not (ROOT / relative).exists():
        raise SystemExit(f"NODE-63 missing required file: {relative}")

engine = (ROOT / "services/project-core/src/lumi_project_core/billing.py").read_text()
router = (ROOT / "apps/api/src/lumi_api/billing_router.py").read_text()
migration = (ROOT / "db/migrations/0013_billing.sql").read_text().lower()
frontend = "\n".join((ROOT / path).read_text() for path in [
    "apps/web/src/components/billing/billing-center.tsx",
    "apps/web/src/lib/billing/billing-gateway.ts",
    "apps/web/src/lib/billing/billing-server.ts",
])

for token in [
    "PlanVersion",
    "CreditLedgerEntry",
    "PricingPolicyVersion",
    "MockPaymentProvider",
    "run_payment_event_once",
    "append_refund",
    "BILLING_INSUFFICIENT_CREDITS",
    "BILLING_WEBHOOK_EVENT_ID_COLLISION",
    "provider_cost_entry_ref",
    "plan_version_id",
]:
    if token not in engine:
        raise SystemExit(f"NODE-63 billing engine contract missing {token}")
for token in [
    "/checkout",
    "/portal",
    "/subscription:cancel",
    "/webhooks/{provider}",
    "X-Lumi-Payment-Signature",
    "payment_provider_name",
]:
    if token not in router:
        raise SystemExit(f"NODE-63 API contract missing {token}")
for table in [
    "billing_plan_versions",
    "billing_pricing_policies",
    "billing_accounts",
    "billing_subscriptions",
    "billing_credit_ledger",
    "billing_usage_records",
    "billing_invoices",
    "billing_payment_events",
]:
    if f"create table if not exists {table}" not in migration:
        raise SystemExit(f"NODE-63 durable table missing: {table}")
if "billing_credit_balances" not in migration:
    raise SystemExit("NODE-63 credit projection view missing")
if "plan_version_id text not null references billing_plan_versions" not in migration:
    raise SystemExit("NODE-63 invoice/subscription exact PlanVersion FK missing")
for forbidden in ["localStorage", "sessionStorage", "indexedDB"]:
    if forbidden in frontend:
        raise SystemExit(f"NODE-63 browser canonical persistence forbidden: {forbidden}")
for forbidden in ["card_number", "cvv", "security_code", "primary_account_number"]:
    if forbidden in (engine + router + migration + frontend).lower():
        raise SystemExit(f"NODE-63 raw payment credential field forbidden: {forbidden}")
server = (ROOT / "apps/web/src/lib/billing/billing-server.ts").read_text()
if 'process.env.NODE_ENV !== "production"' not in server or "LUMI_BILLING_E2E" not in server:
    raise SystemExit("NODE-63 deterministic fixture must be non-production gated")
print("NODE-63 billing architecture contract: OK")
