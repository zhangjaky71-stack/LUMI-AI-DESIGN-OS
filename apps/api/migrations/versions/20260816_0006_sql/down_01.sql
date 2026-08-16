DROP INDEX IF EXISTS ix_idempotency_operations_recovery;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_idempotency_operations_stale_lease;

-- statement-breakpoint

ALTER TABLE idempotency_operations
  DROP CONSTRAINT IF EXISTS ck_idempotency_operations_status,
  DROP CONSTRAINT IF EXISTS ck_idempotency_operations_request_hash,
  DROP CONSTRAINT IF EXISTS ck_idempotency_operations_lease_pair,
  DROP CONSTRAINT IF EXISTS ck_idempotency_operations_response_status,
  DROP CONSTRAINT IF EXISTS ck_idempotency_operations_error_category,
  DROP CONSTRAINT IF EXISTS ck_idempotency_operations_recovery_state,
  DROP CONSTRAINT IF EXISTS ck_idempotency_operations_compensation_mode,
  DROP CONSTRAINT IF EXISTS ck_idempotency_operations_version_positive,
  DROP CONSTRAINT IF EXISTS uq_idempotency_org_operation_key;

-- statement-breakpoint

UPDATE idempotency_operations
SET status = CASE status
  WHEN 'succeeded' THEN 'completed'
  WHEN 'failed_final' THEN 'failed'
  WHEN 'new' THEN 'started'
  WHEN 'in_progress' THEN 'started'
  WHEN 'failed_retryable' THEN 'started'
  ELSE 'failed'
END;

-- statement-breakpoint

ALTER TABLE idempotency_operations ALTER COLUMN status SET DEFAULT 'started';

-- statement-breakpoint

ALTER TABLE idempotency_operations
  ADD CONSTRAINT uq_idempotency_org_key UNIQUE (organization_id, idempotency_key),
  ADD CONSTRAINT ck_idempotency_operations_status
  CHECK (status IN ('started','completed','failed'));

-- statement-breakpoint

ALTER TABLE idempotency_operations
  DROP COLUMN business_scope_id,
  DROP COLUMN side_effect_kind,
  DROP COLUMN compensation_mode,
  DROP COLUMN paid,
  DROP COLUMN lease_owner,
  DROP COLUMN lease_expires_at,
  DROP COLUMN provider_request_id,
  DROP COLUMN result_ref,
  DROP COLUMN response_status,
  DROP COLUMN error_category,
  DROP COLUMN error_code,
  DROP COLUMN error_message,
  DROP COLUMN recovery_state,
  DROP COLUMN recovery_detail,
  DROP COLUMN updated_at,
  DROP COLUMN completed_at,
  DROP COLUMN version;
