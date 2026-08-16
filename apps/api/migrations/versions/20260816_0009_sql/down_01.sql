DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM cost_ledger WHERE entry_type IN ('estimate','reservation')
  ) THEN
    RAISE EXCEPTION 'NODE-27 downgrade refused: estimate/reservation ledger facts cannot map to 0008';
  END IF;
END;
$$;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_ledger_immutable ON cost_ledger;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_ledger_normalize_status ON cost_ledger;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_normalize_cost_status();

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_cost_ledger_same_tenant ON cost_ledger;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS uq_cost_ledger_operation_entry_key;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS ck_cost_ledger_quantity_nonnegative;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS ck_cost_ledger_entry_key;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS ck_cost_ledger_cost_basis;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS ck_cost_ledger_status;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS ck_cost_ledger_confidence;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS ck_cost_ledger_reversal_semantics;

-- statement-breakpoint

ALTER TABLE cost_ledger DROP CONSTRAINT IF EXISTS ck_cost_ledger_entry_type;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_cost_ledger_pricing_snapshot;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_cost_ledger_org_type_occurred;

-- statement-breakpoint

UPDATE cost_ledger SET entry_type='charge' WHERE entry_type='actual_cost';

-- statement-breakpoint

ALTER TABLE cost_ledger
  DROP COLUMN source,
  DROP COLUMN cost_basis,
  DROP COLUMN status,
  DROP COLUMN confidence,
  DROP COLUMN external_provider_request_id,
  DROP COLUMN pricing_snapshot_id,
  DROP COLUMN entry_key;

-- statement-breakpoint

ALTER TABLE cost_ledger RENAME COLUMN reverses_entry_id TO related_entry_id;

-- statement-breakpoint

ALTER TABLE cost_ledger
  ADD CONSTRAINT ck_cost_ledger_entry_type
    CHECK (entry_type IN ('charge','reversal','adjustment')),
  ADD CONSTRAINT ck_cost_ledger_related_entry_semantics
    CHECK (
      (entry_type='charge' AND related_entry_id IS NULL)
      OR (entry_type IN ('reversal','adjustment') AND related_entry_id IS NOT NULL)
    );

-- statement-breakpoint

CREATE UNIQUE INDEX uq_cost_ledger_charge_operation
ON cost_ledger (organization_id, operation_id)
WHERE entry_type='charge' AND operation_id IS NOT NULL;

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

CREATE TRIGGER trg_cost_ledger_immutable
BEFORE UPDATE OR DELETE ON cost_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_forbid_mutation();
