from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"{path}: missing required Stripe billing contract(s): {missing}")


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    present = [needle for needle in needles if needle in text]
    if present:
        raise SystemExit(f"{path}: forbidden Stripe billing contract(s): {present}")


def main() -> None:
    require(
        "apps/api/src/lumi_api/app_v1.py",
        "install_stripe_billing(app)",
    )
    require(
        "apps/api/src/lumi_api/billing_http.py",
        'alias="Stripe-Signature"',
        'permission="billing.manage"',
        "csrf_required=True",
        "PrincipalResolver",
        'resolved.lumi_env not in {"staging", "production"}',
        'raise RuntimeError("LUMI_ALLOWED_ORIGINS is required for Stripe billing")',
        "if not allowed or not origin or origin not in allowed",
    )
    require(
        "apps/api/src/lumi_api/billing_runtime.py",
        "LUMI_STRIPE_SECRET_KEY",
        "LUMI_STRIPE_WEBHOOK_SECRET",
        "LUMI_STRIPE_PLAN_CATALOG_JSON",
        'expected_livemode = environment == "production"',
        "validate_plan_price",
        'plan.currency != "USD"',
        "plan.price_microusd % 10_000",
        "ON CONFLICT (provider, provider_event_id) DO NOTHING",
        "BILLING_WEBHOOK_EVENT_ID_COLLISION",
        "ON CONFLICT (organization_id, idempotency_key) DO NOTHING",
        "pg_advisory_xact_lock",
        "billing-customer:",
    )
    require(
        "services/project-core/src/lumi_project_core/stripe_provider.py",
        'api_version: str = "2026-02-25.clover"',
        'headers["Stripe-Version"]',
        "validate_plan_price",
        "BILLING_STRIPE_PRICE_AMOUNT_MISMATCH",
        "BILLING_STRIPE_PRICE_INTERVAL_MISMATCH",
        "BILLING_STRIPE_PRICE_MODE_MISMATCH",
        "BILLING_STRIPE_EVENT_API_VERSION_MISMATCH",
        "BILLING_STRIPE_CURRENCY_UNSUPPORTED",
        'expected_prefix = "sk_live_" if self.expected_livemode else "sk_test_"',
        "hmac.compare_digest",
        "webhook_tolerance_seconds",
        '("mode", "subscription")',
        "price_ids_by_plan_version",
        'event.get("livemode")',
        'event.get("api_version")',
        'idempotency_key=f"lumi-customer:{organization_id}"[:255]',
        'headers["Idempotency-Key"] = idempotency_key',
    )
    forbid(
        "services/project-core/src/lumi_project_core/stripe_provider.py",
        "line_items[0][amount]",
        "success_url_grants_entitlement",
    )
    require(
        "apps/api/alembic/versions/0019_stripe_billing_runtime.py",
        "CREATE TABLE billing_payment_events",
        "PRIMARY KEY (provider, provider_event_id)",
        "CREATE TABLE billing_credit_ledger",
        "UNIQUE (organization_id, idempotency_key)",
        "FORCE ROW LEVEL SECURITY",
        "trg_billing_credit_immutable",
        "trg_billing_payment_event_immutable",
        "trg_billing_plan_immutable",
        "GRANT SELECT, INSERT ON billing_plan_versions TO lumi_app",
        "GRANT INSERT ON billing_accounts TO lumi_app",
        "GRANT INSERT, UPDATE ON billing_subscriptions TO lumi_app",
        "GRANT INSERT ON billing_payment_events TO lumi_app",
        "GRANT INSERT, UPDATE ON billing_invoices TO lumi_app",
        "GRANT INSERT ON billing_credit_ledger TO lumi_app",
    )
    require(
        "apps/api/src/lumi_api/persistence/models/billing.py",
        "class BillingPlanVersion(Base):",
        "class BillingAccount(Base):",
        "class BillingSubscription(Base):",
        "class BillingPaymentEvent(Base):",
        "class BillingInvoice(Base):",
        "class BillingCreditLedger(Base):",
        "mapped_column(CHAR(3), nullable=False)",
        "mapped_column(CHAR(64), nullable=False)",
        "ix_billing_credit_ledger_org_created",
        "ix_billing_invoices_org_created",
    )
    for environment in ("staging", "production"):
        require(
            f"infra/iac/environments/{environment}/core/main.tf",
            '"billing/stripe-secret-key"',
            '"billing/stripe-webhook-secret"',
        )
        require(
            f"infra/iac/environments/{environment}/app/main.tf",
            "LUMI_ALLOWED_ORIGINS",
            "LUMI_STRIPE_CHECKOUT_SUCCESS_URL",
            "LUMI_STRIPE_CHECKOUT_CANCEL_URL",
            "LUMI_STRIPE_PORTAL_RETURN_URL",
            "LUMI_STRIPE_PLAN_CATALOG_JSON",
            'local.secret_arns["billing/stripe-secret-key"]',
            'local.secret_arns["billing/stripe-webhook-secret"]',
        )
        forbid(
            f"infra/iac/environments/{environment}/app/main.tf",
            "LUMI_BILLING_WEBHOOK_SECRET",
        )
    require(
        "services/project-core/tests/test_stripe_provider.py",
        "test_plan_price_reconciliation_accepts_exact_recurring_contract",
        "test_plan_price_reconciliation_rejects_amount_drift",
        "test_plan_price_reconciliation_rejects_mode_drift",
        "test_webhook_api_version_mismatch_fails_closed",
    )
    require(
        "scripts/integration_stripe_billing_runtime.py",
        "STRIPE_BILLING_POSTGRES_ACCEPTANCE_PASS",
        'path == "/prices/price_acceptance"',
        '"api_version": API_VERSION',
        "transport.customer_posts == 1",
        'duplicate_result.disposition == "DUPLICATE"',
        'error.code == "BILLING_WEBHOOK_EVENT_ID_COLLISION"',
        "has_table_privilege",
        "rls_isolation",
    )
    print("STRIPE_BILLING_STATIC_CONTRACT_PASS")


if __name__ == "__main__":
    main()
