DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM idempotency_operations
    GROUP BY organization_id, idempotency_key
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION 'NODE-20 downgrade blocked: operation-scoped keys collide under NODE-10 uniqueness';
  END IF;
END $$;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_ledger_same_tenant ON cost_ledger;

-- statement-breakpoint

DROP INDEX IF EXISTS uq_cost_ledger_charge_operation;

-- statement-breakpoint

ALTER TABLE cost_ledger
  DROP CONSTRAINT IF EXISTS fk_cost_ledger_operation_id_idempotency_operations;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP COLUMN IF EXISTS operation_id;

-- statement-breakpoint

CREATE TRIGGER trg_cost_ledger_same_tenant
BEFORE INSERT OR UPDATE ON cost_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk(
  'project_id', 'projects',
  'task_id', 'tasks',
  'agent_run_id', 'agent_runs',
  'generation_id', 'generations',
  'related_entry_id', 'cost_ledger',
  'provider_request_id', 'provider_requests'
);
