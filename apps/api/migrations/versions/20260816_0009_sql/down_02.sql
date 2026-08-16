DROP POLICY IF EXISTS tenant_isolation_cost_budget_change_audit ON cost_budget_change_audit;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_quota_leases ON quota_leases;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_quota_limits ON quota_limits;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_cost_reservations ON cost_reservations;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_cost_budget_limits ON cost_budget_limits;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_usage_ledger ON usage_ledger;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_quota_leases_same_tenant ON quota_leases;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_reservations_same_tenant ON cost_reservations;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_usage_ledger_same_tenant ON usage_ledger;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_budget_change_audit_immutable ON cost_budget_change_audit;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_usage_ledger_immutable ON usage_ledger;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_quota_limits_updated_at ON quota_limits;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_budget_limits_updated_at ON cost_budget_limits;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_reservations_updated_at ON cost_reservations;

-- statement-breakpoint

DROP TABLE cost_budget_change_audit;

-- statement-breakpoint

DROP TABLE quota_leases;

-- statement-breakpoint

DROP INDEX IF EXISTS uq_quota_limits_identity;

-- statement-breakpoint

DROP TABLE quota_limits;

-- statement-breakpoint

DROP TABLE cost_reservations;

-- statement-breakpoint

DROP INDEX IF EXISTS uq_cost_budget_limits_identity;

-- statement-breakpoint

DROP TABLE cost_budget_limits;

-- statement-breakpoint

DROP TABLE usage_ledger;
