DROP TRIGGER IF EXISTS trg_cost_ledger_immutable ON cost_ledger;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_ledger_same_tenant ON cost_ledger;

-- statement-breakpoint

DROP INDEX IF EXISTS uq_cost_ledger_charge_operation;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS ck_cost_ledger_entry_type;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS ck_cost_ledger_related_entry_semantics;

-- statement-breakpoint

ALTER TABLE cost_ledger RENAME COLUMN related_entry_id TO reverses_entry_id;

-- statement-breakpoint

ALTER TABLE cost_ledger
  ADD COLUMN entry_key VARCHAR(128) NOT NULL DEFAULT 'primary',
  ADD COLUMN pricing_snapshot_id VARCHAR(128),
  ADD COLUMN external_provider_request_id VARCHAR(512),
  ADD COLUMN confidence VARCHAR(16) NOT NULL DEFAULT 'unknown',
  ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'final',
  ADD COLUMN cost_basis VARCHAR(32) NOT NULL DEFAULT 'provider_cost',
  ADD COLUMN source VARCHAR(64) NOT NULL DEFAULT 'runtime';

-- statement-breakpoint

UPDATE cost_ledger
SET entry_type='actual_cost',
    confidence='unknown',
    status='unknown',
    cost_basis='provider_cost',
    source='legacy_migration'
WHERE entry_type='charge';

-- statement-breakpoint

ALTER TABLE cost_ledger
  ADD CONSTRAINT ck_cost_ledger_entry_type
    CHECK (entry_type IN ('estimate','reservation','actual_cost','reversal','adjustment')),
  ADD CONSTRAINT ck_cost_ledger_reversal_semantics
    CHECK (
      (entry_type IN ('actual_cost','estimate','reservation') AND reverses_entry_id IS NULL)
      OR (entry_type IN ('reversal','adjustment') AND reverses_entry_id IS NOT NULL)
    ),
  ADD CONSTRAINT ck_cost_ledger_confidence
    CHECK (confidence IN ('exact','estimated','unknown')),
  ADD CONSTRAINT ck_cost_ledger_status
    CHECK (status IN ('unknown','estimated','partial','final','reconciled')),
  ADD CONSTRAINT ck_cost_ledger_cost_basis
    CHECK (cost_basis IN ('provider_cost','customer_charge')),
  ADD CONSTRAINT ck_cost_ledger_entry_key
    CHECK (length(entry_key) BETWEEN 1 AND 128),
  ADD CONSTRAINT ck_cost_ledger_quantity_nonnegative
    CHECK (quantity IS NULL OR quantity >= 0),
  ADD CONSTRAINT uq_cost_ledger_operation_entry_key
    UNIQUE (organization_id, operation_id, entry_type, entry_key);

-- statement-breakpoint

CREATE INDEX ix_cost_ledger_org_type_occurred
  ON cost_ledger (organization_id, entry_type, occurred_at);

-- statement-breakpoint

CREATE INDEX ix_cost_ledger_pricing_snapshot
  ON cost_ledger (pricing_snapshot_id) WHERE pricing_snapshot_id IS NOT NULL;

-- statement-breakpoint

CREATE TABLE usage_ledger (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  operation_id UUID NOT NULL REFERENCES idempotency_operations(id) ON DELETE RESTRICT,
  cost_entry_id UUID REFERENCES cost_ledger(id) ON DELETE RESTRICT,
  project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
  task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
  agent_run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,
  generation_id UUID REFERENCES generations(id) ON DELETE SET NULL,
  provider VARCHAR(100),
  model VARCHAR(255),
  external_provider_request_id VARCHAR(512),
  metric VARCHAR(100) NOT NULL,
  entry_key VARCHAR(128) NOT NULL DEFAULT 'primary',
  quantity NUMERIC(30,10) NOT NULL,
  unit VARCHAR(64) NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_usage_ledger_operation_metric_key
    UNIQUE (organization_id, operation_id, metric, entry_key),
  CONSTRAINT ck_usage_ledger_quantity CHECK (quantity >= 0),
  CONSTRAINT ck_usage_ledger_metric CHECK (length(metric) BETWEEN 1 AND 100),
  CONSTRAINT ck_usage_ledger_entry_key CHECK (length(entry_key) BETWEEN 1 AND 128)
);

-- statement-breakpoint

CREATE INDEX ix_usage_ledger_org_occurred
  ON usage_ledger (organization_id, occurred_at);

-- statement-breakpoint

CREATE INDEX ix_usage_ledger_project_occurred
  ON usage_ledger (project_id, occurred_at) WHERE project_id IS NOT NULL;

-- statement-breakpoint

CREATE INDEX ix_usage_ledger_metric_occurred
  ON usage_ledger (organization_id, metric, occurred_at);

-- statement-breakpoint

CREATE TABLE cost_budget_limits (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  scope_type VARCHAR(32) NOT NULL,
  scope_id UUID,
  period_key VARCHAR(32) NOT NULL,
  amount_limit NUMERIC(20,8) NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'USD',
  tolerance_amount NUMERIC(20,8) NOT NULL DEFAULT 0,
  enforcement_mode VARCHAR(16) NOT NULL DEFAULT 'hard',
  enabled BOOLEAN NOT NULL DEFAULT true,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  version INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT ck_cost_budget_limits_scope_type CHECK (
    scope_type IN ('organization','project','agent_run','task','operation')
  ),
  CONSTRAINT ck_cost_budget_limits_scope_identity CHECK (
    (scope_type='organization' AND scope_id IS NULL)
    OR (scope_type<>'organization' AND scope_id IS NOT NULL)
  ),
  CONSTRAINT ck_cost_budget_limits_period_key CHECK (length(period_key) BETWEEN 1 AND 32),
  CONSTRAINT ck_cost_budget_limits_amount CHECK (amount_limit >= 0),
  CONSTRAINT ck_cost_budget_limits_tolerance CHECK (tolerance_amount >= 0),
  CONSTRAINT ck_cost_budget_limits_currency CHECK (currency ~ '^[A-Z]{3}$'),
  CONSTRAINT ck_cost_budget_limits_mode CHECK (enforcement_mode IN ('hard','approval'))
);

-- statement-breakpoint

CREATE UNIQUE INDEX uq_cost_budget_limits_identity ON cost_budget_limits (
  organization_id,
  scope_type,
  COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
  period_key,
  currency
);

-- statement-breakpoint

CREATE INDEX ix_cost_budget_limits_org_scope
  ON cost_budget_limits (organization_id, scope_type, scope_id, period_key);

-- statement-breakpoint

CREATE TABLE cost_reservations (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL REFERENCES idempotency_operations(id) ON DELETE RESTRICT,
  project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
  task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
  agent_run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,
  generation_id UUID REFERENCES generations(id) ON DELETE SET NULL,
  provider VARCHAR(100) NOT NULL,
  model VARCHAR(255) NOT NULL,
  reservation_key VARCHAR(512) NOT NULL,
  estimated_amount NUMERIC(20,8) NOT NULL,
  actual_amount NUMERIC(20,8),
  currency CHAR(3) NOT NULL DEFAULT 'USD',
  pricing_snapshot_id VARCHAR(128),
  confidence VARCHAR(16) NOT NULL DEFAULT 'estimated',
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  expires_at TIMESTAMPTZ NOT NULL,
  committed_at TIMESTAMPTZ,
  released_at TIMESTAMPTZ,
  release_reason VARCHAR(128),
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  version INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT uq_cost_reservations_identity UNIQUE (organization_id, operation_id, reservation_key),
  CONSTRAINT ck_cost_reservations_estimate CHECK (estimated_amount >= 0),
  CONSTRAINT ck_cost_reservations_actual CHECK (actual_amount IS NULL OR actual_amount >= 0),
  CONSTRAINT ck_cost_reservations_currency CHECK (currency ~ '^[A-Z]{3}$'),
  CONSTRAINT ck_cost_reservations_confidence CHECK (confidence IN ('exact','estimated','unknown')),
  CONSTRAINT ck_cost_reservations_status CHECK (
    status IN ('active','committed','released','expired')
  )
);

-- statement-breakpoint

CREATE INDEX ix_cost_reservations_org_active
  ON cost_reservations (organization_id, status, expires_at);

-- statement-breakpoint

CREATE INDEX ix_cost_reservations_project_active
  ON cost_reservations (project_id, status, expires_at) WHERE project_id IS NOT NULL;

-- statement-breakpoint

CREATE TABLE quota_limits (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  scope_type VARCHAR(32) NOT NULL DEFAULT 'organization',
  scope_id UUID,
  metric VARCHAR(100) NOT NULL,
  period_key VARCHAR(32) NOT NULL,
  quantity_limit NUMERIC(30,10) NOT NULL,
  unit VARCHAR(64) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT true,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  version INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT ck_quota_limits_scope_type CHECK (
    scope_type IN ('organization','project','agent_run')
  ),
  CONSTRAINT ck_quota_limits_scope_identity CHECK (
    (scope_type='organization' AND scope_id IS NULL)
    OR (scope_type<>'organization' AND scope_id IS NOT NULL)
  ),
  CONSTRAINT ck_quota_limits_quantity CHECK (quantity_limit >= 0),
  CONSTRAINT ck_quota_limits_metric CHECK (length(metric) BETWEEN 1 AND 100),
  CONSTRAINT ck_quota_limits_period_key CHECK (length(period_key) BETWEEN 1 AND 32)
);

-- statement-breakpoint

CREATE UNIQUE INDEX uq_quota_limits_identity ON quota_limits (
  organization_id,
  scope_type,
  COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid),
  metric,
  period_key
);

-- statement-breakpoint

CREATE TABLE quota_leases (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL REFERENCES idempotency_operations(id) ON DELETE RESTRICT,
  metric VARCHAR(100) NOT NULL,
  quantity NUMERIC(30,10) NOT NULL,
  unit VARCHAR(64) NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  released_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_quota_leases_identity UNIQUE (organization_id, operation_id, metric),
  CONSTRAINT ck_quota_leases_quantity CHECK (quantity > 0)
);

-- statement-breakpoint

CREATE INDEX ix_quota_leases_active
  ON quota_leases (organization_id, metric, expires_at) WHERE released_at IS NULL;

-- statement-breakpoint

CREATE TABLE cost_budget_change_audit (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  budget_limit_id UUID REFERENCES cost_budget_limits(id) ON DELETE SET NULL,
  actor_id VARCHAR(160) NOT NULL,
  action VARCHAR(32) NOT NULL,
  before_json JSONB,
  after_json JSONB,
  reason VARCHAR(1000) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_cost_budget_audit_action CHECK (action IN ('create','update','disable','enable'))
);
