ALTER TABLE idempotency_operations
  ADD COLUMN business_scope_id VARCHAR(255),
  ADD COLUMN side_effect_kind VARCHAR(64) DEFAULT 'generic_write' NOT NULL,
  ADD COLUMN compensation_mode VARCHAR(64) DEFAULT 'non_compensatable' NOT NULL,
  ADD COLUMN paid BOOLEAN DEFAULT false NOT NULL,
  ADD COLUMN lease_owner VARCHAR(160),
  ADD COLUMN lease_expires_at TIMESTAMP WITH TIME ZONE,
  ADD COLUMN provider_request_id VARCHAR(255),
  ADD COLUMN result_ref TEXT,
  ADD COLUMN response_status INTEGER,
  ADD COLUMN error_category VARCHAR(32),
  ADD COLUMN error_code VARCHAR(128),
  ADD COLUMN error_message TEXT,
  ADD COLUMN recovery_state VARCHAR(32) DEFAULT 'none' NOT NULL,
  ADD COLUMN recovery_detail JSONB DEFAULT '{}'::jsonb NOT NULL,
  ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE,
  ADD COLUMN version INTEGER DEFAULT 1 NOT NULL;

-- statement-breakpoint

ALTER TABLE idempotency_operations DROP CONSTRAINT ck_idempotency_operations_status;

-- statement-breakpoint

UPDATE idempotency_operations
SET status = CASE status
  WHEN 'started' THEN 'in_progress'
  WHEN 'completed' THEN 'succeeded'
  WHEN 'failed' THEN 'failed_final'
  ELSE status
END,
updated_at = now(),
completed_at = CASE
  WHEN status IN ('completed','failed') THEN COALESCE(completed_at, now())
  ELSE completed_at
END;

-- statement-breakpoint

ALTER TABLE idempotency_operations ALTER COLUMN status SET DEFAULT 'in_progress';

-- statement-breakpoint

ALTER TABLE idempotency_operations DROP CONSTRAINT uq_idempotency_org_key;

-- statement-breakpoint

ALTER TABLE idempotency_operations
  ADD CONSTRAINT uq_idempotency_org_operation_key
  UNIQUE (organization_id, operation_type, idempotency_key);

-- statement-breakpoint

ALTER TABLE idempotency_operations
  ADD CONSTRAINT ck_idempotency_operations_status
  CHECK (status IN ('new','in_progress','succeeded','failed_retryable','failed_final')),
  ADD CONSTRAINT ck_idempotency_operations_request_hash
  CHECK (request_hash ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT ck_idempotency_operations_lease_pair
  CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
  ADD CONSTRAINT ck_idempotency_operations_response_status
  CHECK (response_status IS NULL OR response_status BETWEEN 100 AND 599),
  ADD CONSTRAINT ck_idempotency_operations_error_category
  CHECK (error_category IS NULL OR error_category IN ('transient','permanent','ambiguous')),
  ADD CONSTRAINT ck_idempotency_operations_recovery_state
  CHECK (recovery_state IN ('none','reconciling','ambiguous')),
  ADD CONSTRAINT ck_idempotency_operations_recovery_consistency
  CHECK (recovery_state <> 'ambiguous' OR error_category = 'ambiguous'),
  ADD CONSTRAINT ck_idempotency_operations_side_effect_kind
  CHECK (side_effect_kind IN (
    'paid_model_invocation','image_generation','video_generation',
    'external_tool_write','object_finalization','billing_charge','billing_credit',
    'email_send','export_creation','external_publish','generic_write'
  )),
  ADD CONSTRAINT ck_idempotency_operations_compensation_mode
  CHECK (compensation_mode IN ('compensatable','non_compensatable','reversible_by_new_operation')),
  ADD CONSTRAINT ck_idempotency_operations_terminal_completion
  CHECK ((status IN ('succeeded','failed_final')) = (completed_at IS NOT NULL)),
  ADD CONSTRAINT ck_idempotency_operations_version_positive
  CHECK (version >= 1);

-- statement-breakpoint

CREATE INDEX ix_idempotency_operations_stale_lease
ON idempotency_operations (organization_id, lease_expires_at)
WHERE status = 'in_progress';

-- statement-breakpoint

CREATE INDEX ix_idempotency_operations_recovery
ON idempotency_operations (organization_id, recovery_state, updated_at)
WHERE recovery_state <> 'none';

-- statement-breakpoint

ALTER TABLE idempotency_operations ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_idempotency_operations ON idempotency_operations;

-- statement-breakpoint

CREATE POLICY tenant_isolation_idempotency_operations ON idempotency_operations
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());
