DROP TABLE IF EXISTS governance_audit_exports;

-- statement-breakpoint

DROP TABLE IF EXISTS governance_deletion_requests;

-- statement-breakpoint

DROP TABLE IF EXISTS governance_legal_holds;

-- statement-breakpoint

DROP TABLE IF EXISTS governance_retention_policies;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events;

-- statement-breakpoint

DROP FUNCTION IF EXISTS governance_reject_audit_mutation();

-- statement-breakpoint

DROP INDEX IF EXISTS ix_audit_events_org_trace;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_audit_events_org_resource_occurred;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_audit_events_org_action_occurred;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_audit_events_org_actor_occurred;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_audit_events_org_occurred;

-- statement-breakpoint

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS fk_audit_events_task_ref;

-- statement-breakpoint

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS fk_audit_events_agent_run_ref;

-- statement-breakpoint

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS fk_audit_events_api_token_ref;

-- statement-breakpoint

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS ck_audit_events_resource_version;

-- statement-breakpoint

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS ck_audit_events_retention_class;

-- statement-breakpoint

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS ck_audit_events_result;

-- statement-breakpoint

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS ck_audit_events_event_hash;

-- statement-breakpoint

ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS ck_audit_events_actor_type;

-- statement-breakpoint

ALTER TABLE audit_events ALTER COLUMN actor_id DROP NOT NULL;

-- statement-breakpoint

ALTER TABLE audit_events
  DROP COLUMN IF EXISTS occurred_at,
  DROP COLUMN IF EXISTS retention_policy_version,
  DROP COLUMN IF EXISTS retention_class,
  DROP COLUMN IF EXISTS change_summary_json,
  DROP COLUMN IF EXISTS security_metadata_json,
  DROP COLUMN IF EXISTS trace_id,
  DROP COLUMN IF EXISTS request_id,
  DROP COLUMN IF EXISTS reason_code,
  DROP COLUMN IF EXISTS result,
  DROP COLUMN IF EXISTS resource_version,
  DROP COLUMN IF EXISTS task_ref,
  DROP COLUMN IF EXISTS agent_run_ref,
  DROP COLUMN IF EXISTS api_token_ref,
  DROP COLUMN IF EXISTS session_ref;
