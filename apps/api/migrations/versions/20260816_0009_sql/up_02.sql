CREATE OR REPLACE FUNCTION lumi_normalize_cost_status() RETURNS trigger AS $$
BEGIN
  IF NEW.entry_type = 'actual_cost' THEN
    NEW.status := CASE NEW.confidence
      WHEN 'exact' THEN 'final'
      WHEN 'estimated' THEN 'estimated'
      ELSE 'unknown'
    END;
  ELSIF NEW.entry_type IN ('adjustment','reversal') THEN
    NEW.status := 'reconciled';
  ELSIF NEW.entry_type IN ('estimate','reservation') THEN
    NEW.status := 'estimated';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- statement-breakpoint

CREATE TRIGGER trg_cost_ledger_normalize_status
BEFORE INSERT ON cost_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_normalize_cost_status();

-- statement-breakpoint

CREATE TRIGGER trg_cost_ledger_immutable
BEFORE UPDATE OR DELETE ON cost_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_forbid_mutation();

-- statement-breakpoint

CREATE TRIGGER trg_usage_ledger_immutable
BEFORE UPDATE OR DELETE ON usage_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_forbid_mutation();

-- statement-breakpoint

CREATE TRIGGER trg_cost_budget_change_audit_immutable
BEFORE UPDATE OR DELETE ON cost_budget_change_audit
FOR EACH ROW EXECUTE FUNCTION lumi_forbid_mutation();

-- statement-breakpoint

CREATE TRIGGER trg_cost_reservations_updated_at
BEFORE UPDATE ON cost_reservations
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_cost_budget_limits_updated_at
BEFORE UPDATE ON cost_budget_limits
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_quota_limits_updated_at
BEFORE UPDATE ON quota_limits
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_cost_ledger_same_tenant
BEFORE INSERT OR UPDATE ON cost_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk(
  'project_id', 'projects',
  'task_id', 'tasks',
  'agent_run_id', 'agent_runs',
  'generation_id', 'generations',
  'reverses_entry_id', 'cost_ledger',
  'provider_request_id', 'provider_requests',
  'operation_id', 'idempotency_operations'
);

-- statement-breakpoint

CREATE TRIGGER trg_usage_ledger_same_tenant
BEFORE INSERT OR UPDATE ON usage_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk(
  'operation_id', 'idempotency_operations',
  'cost_entry_id', 'cost_ledger',
  'project_id', 'projects',
  'task_id', 'tasks',
  'agent_run_id', 'agent_runs',
  'generation_id', 'generations'
);

-- statement-breakpoint

CREATE TRIGGER trg_cost_reservations_same_tenant
BEFORE INSERT OR UPDATE ON cost_reservations
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk(
  'operation_id', 'idempotency_operations',
  'project_id', 'projects',
  'task_id', 'tasks',
  'agent_run_id', 'agent_runs',
  'generation_id', 'generations'
);

-- statement-breakpoint

CREATE TRIGGER trg_quota_leases_same_tenant
BEFORE INSERT OR UPDATE ON quota_leases
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('operation_id', 'idempotency_operations');

-- statement-breakpoint

ALTER TABLE usage_ledger ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_usage_ledger ON usage_ledger
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE cost_budget_limits ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_cost_budget_limits ON cost_budget_limits
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE cost_reservations ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_cost_reservations ON cost_reservations
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE quota_limits ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_quota_limits ON quota_limits
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE quota_leases ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_quota_leases ON quota_leases
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE cost_budget_change_audit ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_cost_budget_change_audit ON cost_budget_change_audit
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

GRANT SELECT, INSERT ON cost_ledger TO lumi_app;

-- statement-breakpoint

REVOKE UPDATE, DELETE ON cost_ledger FROM lumi_app;

-- statement-breakpoint

GRANT SELECT, INSERT ON usage_ledger TO lumi_app;

-- statement-breakpoint

REVOKE UPDATE, DELETE ON usage_ledger FROM lumi_app;

-- statement-breakpoint

GRANT SELECT, INSERT, UPDATE ON cost_reservations TO lumi_app;

-- statement-breakpoint

REVOKE DELETE ON cost_reservations FROM lumi_app;

-- statement-breakpoint

GRANT SELECT ON cost_budget_limits, quota_limits TO lumi_app;

-- statement-breakpoint

REVOKE INSERT, UPDATE, DELETE ON cost_budget_limits, quota_limits FROM lumi_app;

-- statement-breakpoint

GRANT SELECT, INSERT, UPDATE ON quota_leases TO lumi_app;

-- statement-breakpoint

REVOKE DELETE ON quota_leases FROM lumi_app;

-- statement-breakpoint

GRANT SELECT ON cost_budget_change_audit TO lumi_app;

-- statement-breakpoint

REVOKE INSERT, UPDATE, DELETE ON cost_budget_change_audit FROM lumi_app;
