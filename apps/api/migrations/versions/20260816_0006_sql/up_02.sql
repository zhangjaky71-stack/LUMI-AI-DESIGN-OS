ALTER TABLE cost_ledger ADD COLUMN operation_id UUID;

-- statement-breakpoint

ALTER TABLE cost_ledger
  ADD CONSTRAINT fk_cost_ledger_operation_id_idempotency_operations
  FOREIGN KEY (operation_id) REFERENCES idempotency_operations(id) ON DELETE RESTRICT;

-- statement-breakpoint

CREATE UNIQUE INDEX uq_cost_ledger_charge_operation
ON cost_ledger (organization_id, operation_id)
WHERE entry_type = 'charge' AND operation_id IS NOT NULL;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_ledger_same_tenant ON cost_ledger;

-- statement-breakpoint

CREATE TRIGGER trg_cost_ledger_same_tenant
BEFORE INSERT OR UPDATE ON cost_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk(
  'project_id', 'projects',
  'task_id', 'tasks',
  'agent_run_id', 'agent_runs',
  'generation_id', 'generations',
  'related_entry_id', 'cost_ledger',
  'provider_request_id', 'provider_requests',
  'operation_id', 'idempotency_operations'
);

-- statement-breakpoint

GRANT SELECT, INSERT, UPDATE ON idempotency_operations TO lumi_app;

-- statement-breakpoint

REVOKE DELETE ON idempotency_operations FROM lumi_app;

-- statement-breakpoint

GRANT SELECT, INSERT ON cost_ledger TO lumi_app;

-- statement-breakpoint

REVOKE UPDATE, DELETE ON cost_ledger FROM lumi_app;
