BEGIN;

CREATE TABLE IF NOT EXISTS billing_plan_versions (
  plan_version_id text PRIMARY KEY,
  plan_id text NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  name text NOT NULL,
  currency char(3) NOT NULL,
  price_microusd bigint NOT NULL CHECK (price_microusd >= 0),
  billing_interval text NOT NULL CHECK (billing_interval IN ('MONTH','YEAR')),
  monthly_credit_grant bigint NOT NULL CHECK (monthly_credit_grant >= 0),
  entitlements jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(entitlements) = 'object'),
  status text NOT NULL CHECK (status IN ('ACTIVE','ARCHIVED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (plan_id, version)
);

CREATE TABLE IF NOT EXISTS billing_pricing_policies (
  policy_id text NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  rules jsonb NOT NULL CHECK (jsonb_typeof(rules) = 'array'),
  status text NOT NULL CHECK (status IN ('ACTIVE','ARCHIVED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS billing_accounts (
  organization_id uuid PRIMARY KEY,
  payment_provider text NOT NULL,
  payment_customer_ref text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (payment_provider, payment_customer_ref)
);

CREATE TABLE IF NOT EXISTS billing_subscriptions (
  subscription_id text PRIMARY KEY,
  organization_id uuid NOT NULL UNIQUE,
  plan_version_id text NOT NULL REFERENCES billing_plan_versions(plan_version_id),
  payment_provider text NOT NULL,
  provider_subscription_ref text NOT NULL,
  state text NOT NULL CHECK (state IN ('TRIALING','ACTIVE','PAST_DUE','CANCEL_AT_PERIOD_END','CANCELLED','INCOMPLETE')),
  current_period_start timestamptz NULL,
  current_period_end timestamptz NULL,
  cancel_at_period_end boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (payment_provider, provider_subscription_ref)
);

CREATE TABLE IF NOT EXISTS billing_credit_ledger (
  entry_id text PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id text NULL,
  entry_type text NOT NULL CHECK (entry_type IN ('GRANT','CONSUME','REFUND','EXPIRE','ADJUSTMENT','REVERSAL')),
  delta_credits bigint NOT NULL CHECK (delta_credits <> 0),
  source_type text NOT NULL,
  source_id text NOT NULL,
  pricing_policy_version integer NULL,
  usage_record_id text NULL,
  reverses_entry_id text NULL REFERENCES billing_credit_ledger(entry_id),
  idempotency_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, idempotency_key),
  CHECK ((entry_type IN ('CONSUME','EXPIRE') AND delta_credits < 0) OR entry_type NOT IN ('CONSUME','EXPIRE')),
  CHECK ((entry_type IN ('GRANT','REFUND') AND delta_credits > 0) OR entry_type NOT IN ('GRANT','REFUND'))
);
CREATE INDEX IF NOT EXISTS billing_credit_ledger_org_idx
  ON billing_credit_ledger (organization_id, created_at DESC);

CREATE TABLE IF NOT EXISTS billing_usage_records (
  usage_record_id text PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id text NULL,
  usage_key text NOT NULL,
  quantity numeric(38,12) NOT NULL CHECK (quantity > 0),
  unit text NOT NULL,
  credits_consumed bigint NOT NULL CHECK (credits_consumed > 0),
  pricing_policy_version integer NOT NULL,
  credit_entry_id text NOT NULL REFERENCES billing_credit_ledger(entry_id),
  provider_cost_entry_ref text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, credit_entry_id)
);

CREATE TABLE IF NOT EXISTS billing_invoices (
  invoice_id text PRIMARY KEY,
  organization_id uuid NOT NULL,
  provider text NOT NULL,
  provider_invoice_ref text NOT NULL,
  plan_version_id text NOT NULL REFERENCES billing_plan_versions(plan_version_id),
  status text NOT NULL CHECK (status IN ('PAID','OPEN','FAILED','VOID')),
  amount_due_microusd bigint NOT NULL CHECK (amount_due_microusd >= 0),
  currency char(3) NOT NULL,
  hosted_invoice_url text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_invoice_ref)
);
CREATE INDEX IF NOT EXISTS billing_invoices_org_idx
  ON billing_invoices (organization_id, created_at DESC);

CREATE TABLE IF NOT EXISTS billing_payment_events (
  provider text NOT NULL,
  provider_event_id text NOT NULL,
  organization_id uuid NOT NULL,
  event_type text NOT NULL,
  payload_hash char(64) NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (provider, provider_event_id)
);

CREATE OR REPLACE VIEW billing_credit_balances AS
SELECT organization_id, COALESCE(SUM(delta_credits), 0)::bigint AS balance
FROM billing_credit_ledger
GROUP BY organization_id;

COMMIT;
