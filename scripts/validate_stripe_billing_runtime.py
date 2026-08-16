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
    )
    require(
        "apps/api/src/lumi_api/billing_runtime.py",
        "LUMI_STRIPE_SECRET_KEY",
        "LUMI_STRIPE_WEBHOOK_SECRET",
        "LUMI_STRIPE_PLAN_CATALOG_JSON",
        'expected_livemode = environment == "production"',
        "ON CONFLICT (provider, provider_event_id) DO NOTHING",
        "BILLING_WEBHOOK_EVENT_ID_COLLISION",
        "ON CONFLICT (organization_id, idempotency_key) DO NOTHING",
    )
    require(
        "services/project-core/src/lumi_project_core/stripe_provider.py",
        'expected_prefix = "sk_live_" if self.expected_livemode else "sk_test_"',
        "hmac.compare_digest",
        "webhook_tolerance_seconds",
        '("mode", "subscription")',
        'price_ids_by_plan_version',
        'event.get("livemode")',
    )
    forbid(
        "services/project-core/src/lumi_project_core/stripe_provider.py",
        'line_items[0][amount]',
        'success_url_grants_entitlement',
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
    )
    print("STRIPE_BILLING_STATIC_CONTRACT_PASS")


if __name__ == "__main__":
    main()
