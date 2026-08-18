CREATE TABLE billing_plans (
    id UUID PRIMARY KEY,
    plan_key VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);

-- statement-breakpoint

CREATE TABLE billing_plan_versions (
    id UUID PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES billing_plans(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL,
    currency VARCHAR(3) NOT NULL,
    monthly_price NUMERIC(20,8) NOT NULL,
    included_credits NUMERIC(30,8) NOT NULL,
    postpaid_allowed BOOLEAN NOT NULL DEFAULT false,
    entitlements_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    pricing_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    effective_at TIMESTAMPTZ NOT NULL,
    retired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_billing_plan_version UNIQUE (plan_id, version),
    CONSTRAINT ck_billing_plan_version_number CHECK (version >= 1),
    CONSTRAINT ck_billing_plan_version_currency CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_billing_plan_version_price CHECK (monthly_price >= 0),
    CONSTRAINT ck_billing_plan_version_credits CHECK (included_credits >= 0)
);

-- statement-breakpoint

CREATE TABLE billing_accounts (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    provider VARCHAR(40) NOT NULL,
    provider_customer_ref VARCHAR(255) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT uq_billing_account_provider UNIQUE (organization_id, provider),
    CONSTRAINT uq_billing_provider_customer UNIQUE (provider, provider_customer_ref),
    CONSTRAINT ck_billing_account_status CHECK (status IN ('ACTIVE','SUSPENDED','CLOSED'))
);

-- statement-breakpoint

CREATE TABLE billing_subscriptions (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    billing_account_id UUID NOT NULL REFERENCES billing_accounts(id) ON DELETE CASCADE,
    plan_version_id UUID NOT NULL REFERENCES billing_plan_versions(id) ON DELETE RESTRICT,
    provider VARCHAR(40) NOT NULL,
    provider_subscription_ref VARCHAR(255) NOT NULL,
    state VARCHAR(32) NOT NULL,
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT uq_billing_provider_subscription UNIQUE (provider, provider_subscription_ref),
    CONSTRAINT ck_billing_subscription_state CHECK (
        state IN ('TRIALING','ACTIVE','PAST_DUE','CANCEL_AT_PERIOD_END','CANCELLED','INCOMPLETE')
    ),
    CONSTRAINT ck_billing_subscription_period CHECK (
        current_period_start IS NULL OR current_period_end IS NULL OR current_period_end >= current_period_start
    )
);

-- statement-breakpoint

CREATE INDEX ix_billing_subscriptions_org_state
ON billing_subscriptions (organization_id, state, updated_at DESC);

-- statement-breakpoint

CREATE TABLE billing_credit_wallets (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    cached_balance NUMERIC(30,8) NOT NULL DEFAULT 0,
    allow_postpaid BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT uq_billing_credit_wallet_org UNIQUE (organization_id)
);

-- statement-breakpoint

CREATE TABLE billing_credit_ledger (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    wallet_id UUID NOT NULL REFERENCES billing_credit_wallets(id) ON DELETE RESTRICT,
    operation_id UUID NOT NULL,
    event_type VARCHAR(24) NOT NULL,
    amount NUMERIC(30,8) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    reference_type VARCHAR(80),
    reference_id VARCHAR(255),
    pricing_policy_version VARCHAR(160),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_billing_credit_operation UNIQUE (organization_id, operation_id),
    CONSTRAINT ck_billing_credit_event_type CHECK (
        event_type IN ('GRANT','CONSUME','REFUND','EXPIRE','ADJUSTMENT','REVERSAL')
    ),
    CONSTRAINT ck_billing_credit_signed_amount CHECK (
        (event_type IN ('GRANT','REFUND') AND amount > 0)
        OR (event_type IN ('CONSUME','EXPIRE') AND amount < 0)
        OR (event_type IN ('ADJUSTMENT','REVERSAL') AND amount <> 0)
    )
);

-- statement-breakpoint

CREATE INDEX ix_billing_credit_ledger_org_created
ON billing_credit_ledger (organization_id, created_at DESC, id DESC);

-- statement-breakpoint

CREATE TABLE billing_invoice_refs (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    billing_account_id UUID NOT NULL REFERENCES billing_accounts(id) ON DELETE CASCADE,
    provider VARCHAR(40) NOT NULL,
    provider_invoice_ref VARCHAR(255) NOT NULL,
    status VARCHAR(40) NOT NULL,
    amount_due NUMERIC(20,8) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    hosted_invoice_url TEXT,
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_billing_provider_invoice UNIQUE (provider, provider_invoice_ref),
    CONSTRAINT ck_billing_invoice_amount CHECK (amount_due >= 0),
    CONSTRAINT ck_billing_invoice_currency CHECK (currency ~ '^[A-Z]{3}$')
);

-- statement-breakpoint

CREATE INDEX ix_billing_invoice_refs_org_created
ON billing_invoice_refs (organization_id, created_at DESC);

-- statement-breakpoint

CREATE TABLE billing_payment_events (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    provider VARCHAR(40) NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    body_sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'RECEIVED',
    rejection_code VARCHAR(160),
    occurred_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT uq_billing_provider_event UNIQUE (provider, provider_event_id),
    CONSTRAINT ck_billing_payment_event_hash CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_billing_payment_event_status CHECK (status IN ('RECEIVED','APPLIED','REJECTED'))
);

-- statement-breakpoint

CREATE INDEX ix_billing_payment_events_status
ON billing_payment_events (status, created_at);

-- statement-breakpoint

CREATE OR REPLACE FUNCTION billing_reject_credit_ledger_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'billing_credit_ledger is immutable';
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_billing_credit_ledger_immutable
BEFORE UPDATE OR DELETE ON billing_credit_ledger
FOR EACH ROW EXECUTE FUNCTION billing_reject_credit_ledger_mutation();

-- statement-breakpoint

CREATE OR REPLACE FUNCTION billing_guard_plan_version_material_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.plan_id IS DISTINCT FROM OLD.plan_id
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.currency IS DISTINCT FROM OLD.currency
       OR NEW.monthly_price IS DISTINCT FROM OLD.monthly_price
       OR NEW.included_credits IS DISTINCT FROM OLD.included_credits
       OR NEW.postpaid_allowed IS DISTINCT FROM OLD.postpaid_allowed
       OR NEW.entitlements_json IS DISTINCT FROM OLD.entitlements_json
       OR NEW.pricing_policy_json IS DISTINCT FROM OLD.pricing_policy_json
       OR NEW.effective_at IS DISTINCT FROM OLD.effective_at THEN
        RAISE EXCEPTION 'billing_plan_versions material fields are immutable; create a new version';
    END IF;
    RETURN NEW;
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_billing_plan_version_material_immutable
BEFORE UPDATE ON billing_plan_versions
FOR EACH ROW EXECUTE FUNCTION billing_guard_plan_version_material_update();
