"""Add durable billing state required by the Stripe production runtime.

Revision ID: 0019_stripe_billing_runtime
Revises: 0018_provider_daily_cost_hard_stop
"""

from __future__ import annotations

from alembic import op

revision = "0019_stripe_billing_runtime"
down_revision = "0018_provider_daily_cost_hard_stop"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "billing_accounts",
    "billing_subscriptions",
    "billing_payment_events",
    "billing_invoices",
    "billing_credit_ledger",
)


def upgrade() -> None:
    op.execute("""
    CREATE TABLE billing_plan_versions (
      plan_version_id varchar(120) PRIMARY KEY,
      plan_id varchar(120) NOT NULL,
      version integer NOT NULL CHECK (version > 0),
      name varchar(200) NOT NULL,
      currency char(3) NOT NULL,
      price_microusd bigint NOT NULL CHECK (price_microusd >= 0),
      billing_interval varchar(10) NOT NULL CHECK (billing_interval IN ('MONTH','YEAR')),
      monthly_credit_grant bigint NOT NULL CHECK (monthly_credit_grant >= 0),
      entitlements jsonb NOT NULL DEFAULT '{}'::jsonb,
      status varchar(16) NOT NULL CHECK (status IN ('ACTIVE','ARCHIVED')),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (plan_id, version)
    )
    """)
    op.execute("""
    CREATE FUNCTION lumi_billing_plan_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      RAISE EXCEPTION 'BILLING_PLAN_VERSION_IMMUTABLE' USING ERRCODE='P0001';
    END; $$
    """)
    op.execute("""
    CREATE TRIGGER trg_billing_plan_immutable
    BEFORE UPDATE OR DELETE ON billing_plan_versions
    FOR EACH ROW EXECUTE FUNCTION lumi_billing_plan_immutable()
    """)
    op.execute("""
    CREATE TABLE billing_accounts (
      organization_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE RESTRICT,
      payment_provider varchar(40) NOT NULL,
      payment_customer_ref varchar(255) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (payment_provider, payment_customer_ref)
    )
    """)
    op.execute("""
    CREATE TABLE billing_subscriptions (
      subscription_id varchar(255) PRIMARY KEY,
      organization_id uuid NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE RESTRICT,
      plan_version_id varchar(120) NOT NULL REFERENCES billing_plan_versions(plan_version_id),
      payment_provider varchar(40) NOT NULL,
      provider_subscription_ref varchar(255) NOT NULL UNIQUE,
      state varchar(32) NOT NULL CHECK (state IN ('TRIALING','ACTIVE','PAST_DUE','CANCEL_AT_PERIOD_END','CANCELLED','INCOMPLETE')),
      current_period_start timestamptz,
      current_period_end timestamptz,
      cancel_at_period_end boolean NOT NULL DEFAULT false,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """)
    op.execute("""
    CREATE TABLE billing_payment_events (
      provider varchar(40) NOT NULL,
      provider_event_id varchar(255) NOT NULL,
      organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
      event_type varchar(64) NOT NULL,
      payload_hash char(64) NOT NULL,
      received_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (provider, provider_event_id)
    )
    """)
    op.execute("""
    CREATE TABLE billing_invoices (
      invoice_id varchar(512) PRIMARY KEY,
      organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
      provider varchar(40) NOT NULL,
      provider_invoice_ref varchar(255) NOT NULL,
      plan_version_id varchar(120) NOT NULL REFERENCES billing_plan_versions(plan_version_id),
      status varchar(16) NOT NULL CHECK (status IN ('PAID','OPEN','FAILED','VOID')),
      amount_due_microusd bigint NOT NULL CHECK (amount_due_microusd >= 0),
      currency char(3) NOT NULL,
      hosted_invoice_url text,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (provider, provider_invoice_ref)
    )
    """)
    op.execute("""
    CREATE TABLE billing_credit_ledger (
      entry_id uuid PRIMARY KEY,
      organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
      entry_type varchar(24) NOT NULL CHECK (entry_type IN ('GRANT','CONSUME','REFUND','EXPIRE','ADJUSTMENT','REVERSAL')),
      delta_credits bigint NOT NULL CHECK (delta_credits <> 0),
      source_type varchar(64) NOT NULL,
      source_id varchar(255) NOT NULL,
      pricing_policy_version integer,
      idempotency_key varchar(512) NOT NULL,
      project_id uuid,
      usage_record_id varchar(255),
      reverses_entry_id uuid REFERENCES billing_credit_ledger(entry_id),
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (organization_id, idempotency_key)
    )
    """)
    op.execute(
        "CREATE INDEX ix_billing_credit_ledger_org_created "
        "ON billing_credit_ledger(organization_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_billing_invoices_org_created "
        "ON billing_invoices(organization_id, created_at DESC)"
    )

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
        CREATE POLICY {table}_tenant_policy ON {table}
        USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)
        """)

    op.execute("""
    CREATE FUNCTION lumi_billing_credit_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      RAISE EXCEPTION 'BILLING_CREDIT_LEDGER_IMMUTABLE' USING ERRCODE='P0001';
    END; $$
    """)
    op.execute("""
    CREATE TRIGGER trg_billing_credit_immutable
    BEFORE UPDATE OR DELETE ON billing_credit_ledger
    FOR EACH ROW EXECUTE FUNCTION lumi_billing_credit_immutable()
    """)
    op.execute("""
    CREATE FUNCTION lumi_billing_payment_event_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      RAISE EXCEPTION 'BILLING_PAYMENT_EVENT_IMMUTABLE' USING ERRCODE='P0001';
    END; $$
    """)
    op.execute("""
    CREATE TRIGGER trg_billing_payment_event_immutable
    BEFORE UPDATE OR DELETE ON billing_payment_events
    FOR EACH ROW EXECUTE FUNCTION lumi_billing_payment_event_immutable()
    """)

    # NODE-03 defaults deliberately give newly migrated tables SELECT-only access.
    # Billing therefore opts into the minimum DML required by each runtime operation.
    op.execute("""
    REVOKE INSERT, UPDATE, DELETE ON
      billing_plan_versions,
      billing_accounts,
      billing_subscriptions,
      billing_payment_events,
      billing_invoices,
      billing_credit_ledger
    FROM lumi_app
    """)
    op.execute("GRANT SELECT, INSERT ON billing_plan_versions TO lumi_app")
    op.execute("GRANT INSERT ON billing_accounts TO lumi_app")
    op.execute("GRANT INSERT, UPDATE ON billing_subscriptions TO lumi_app")
    op.execute("GRANT INSERT ON billing_payment_events TO lumi_app")
    op.execute("GRANT INSERT, UPDATE ON billing_invoices TO lumi_app")
    op.execute("GRANT INSERT ON billing_credit_ledger TO lumi_app")
    op.execute("REVOKE ALL ON FUNCTION lumi_billing_plan_immutable() FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION lumi_billing_credit_immutable() FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION lumi_billing_payment_event_immutable() FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_billing_payment_event_immutable ON billing_payment_events")
    op.execute("DROP FUNCTION IF EXISTS lumi_billing_payment_event_immutable()")
    op.execute("DROP TRIGGER IF EXISTS trg_billing_credit_immutable ON billing_credit_ledger")
    op.execute("DROP FUNCTION IF EXISTS lumi_billing_credit_immutable()")
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP TRIGGER IF EXISTS trg_billing_plan_immutable ON billing_plan_versions")
    op.execute("DROP FUNCTION IF EXISTS lumi_billing_plan_immutable()")
    op.execute("DROP TABLE IF EXISTS billing_plan_versions")
