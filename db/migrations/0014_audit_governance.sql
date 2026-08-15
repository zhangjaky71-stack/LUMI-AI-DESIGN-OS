BEGIN;

CREATE TABLE IF NOT EXISTS governance_retention_policies (
  retention_class text NOT NULL CHECK (retention_class IN ('SECURITY_AUDIT','BILLING','CONTENT','AGENT_TRACE','TEMP_SANDBOX','EXPORT','ANALYTICS')),
  version integer NOT NULL CHECK (version > 0),
  retention_days integer NOT NULL CHECK (retention_days > 0 AND retention_days <= 36500),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  policy_note text NOT NULL,
  PRIMARY KEY (retention_class, version)
);

INSERT INTO governance_retention_policies
  (retention_class, version, retention_days, created_by, policy_note)
VALUES
  ('SECURITY_AUDIT', 1, 2555, 'system:node-65-default', 'Engineering default; legal review required before production launch.'),
  ('BILLING',        1, 2555, 'system:node-65-default', 'Engineering default; legal review required before production launch.'),
  ('CONTENT',        1, 365,  'system:node-65-default', 'Engineering default; legal review required before production launch.'),
  ('AGENT_TRACE',    1, 90,   'system:node-65-default', 'Engineering default; legal review required before production launch.'),
  ('TEMP_SANDBOX',   1, 7,    'system:node-65-default', 'Engineering default; legal review required before production launch.'),
  ('EXPORT',         1, 30,   'system:node-65-default', 'Engineering default; legal review required before production launch.'),
  ('ANALYTICS',      1, 400,  'system:node-65-default', 'Engineering default; legal review required before production launch.')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS audit_events (
  event_id text PRIMARY KEY,
  organization_id uuid NULL,
  actor_type text NOT NULL CHECK (actor_type IN ('USER','PLATFORM_ADMIN','AGENT','SERVICE')),
  actor_id text NOT NULL,
  actor_version text NULL,
  session_ref text NULL,
  api_token_ref text NULL,
  agent_run_ref text NULL,
  task_ref text NULL,
  human_initiator_id text NULL,
  action text NOT NULL,
  resource_type text NOT NULL,
  resource_id text NOT NULL,
  resource_version text NULL,
  result text NOT NULL CHECK (result IN ('SUCCESS','DENIED','FAILED')),
  reason_code text NOT NULL,
  request_id text NULL,
  trace_id text NULL,
  security_metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(security_metadata) = 'object'),
  changed_fields jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(changed_fields) = 'array'),
  version_refs jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(version_refs) = 'array'),
  semantic_diff_ref text NULL,
  evidence_ref text NULL,
  retention_class text NOT NULL CHECK (retention_class IN ('SECURITY_AUDIT','BILLING','CONTENT','AGENT_TRACE','TEMP_SANDBOX','EXPORT','ANALYTICS')),
  retention_policy_version integer NOT NULL CHECK (retention_policy_version > 0),
  correction_of_event_id text NULL REFERENCES audit_events(event_id),
  occurred_at timestamptz NOT NULL,
  prev_hash char(64) NULL,
  event_hash char(64) NOT NULL,
  CHECK (
    actor_type <> 'AGENT'
    OR (actor_version IS NOT NULL AND agent_run_ref IS NOT NULL AND task_ref IS NOT NULL AND human_initiator_id IS NOT NULL)
  ),
  FOREIGN KEY (retention_class, retention_policy_version)
    REFERENCES governance_retention_policies(retention_class, version)
);
CREATE INDEX IF NOT EXISTS audit_events_org_time_idx ON audit_events (organization_id, occurred_at DESC, event_id DESC);
CREATE INDEX IF NOT EXISTS audit_events_actor_time_idx ON audit_events (actor_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_action_time_idx ON audit_events (action, occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_resource_idx ON audit_events (resource_type, resource_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_trace_idx ON audit_events (trace_id) WHERE trace_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS audit_events_org_chain_hash_idx ON audit_events ((COALESCE(organization_id::text, '__platform__')), event_hash);

CREATE TABLE IF NOT EXISTS governance_legal_hold_events (
  hold_event_id text PRIMARY KEY,
  hold_id text NOT NULL,
  hold_type text NOT NULL CHECK (hold_type IN ('LEGAL','BILLING')),
  action text NOT NULL CHECK (action IN ('CREATE','RELEASE')),
  organization_id uuid NULL,
  scope_type text NOT NULL CHECK (scope_type IN ('USER','ORGANIZATION','RESOURCE','RETENTION_CLASS')),
  scope_id text NOT NULL,
  reason_code text NOT NULL,
  ticket_ref text NOT NULL,
  actor_id text NOT NULL,
  occurred_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS governance_hold_events_hold_idx ON governance_legal_hold_events (hold_id, occurred_at);
CREATE INDEX IF NOT EXISTS governance_hold_events_org_idx ON governance_legal_hold_events (organization_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS governance_deletion_events (
  deletion_event_id text PRIMARY KEY,
  request_id text NOT NULL,
  subject_user_id text NOT NULL,
  organization_id uuid NOT NULL,
  status text NOT NULL CHECK (status IN ('REQUESTED','BLOCKED_HOLD','DEACTIVATED','DELETING','COMPLETED','FAILED')),
  resource_refs jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(resource_refs) = 'array'),
  blocked_hold_ids jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(blocked_hold_ids) = 'array'),
  deleted_count integer NOT NULL DEFAULT 0 CHECK (deleted_count >= 0),
  anonymized_count integer NOT NULL DEFAULT 0 CHECK (anonymized_count >= 0),
  retained_count integer NOT NULL DEFAULT 0 CHECK (retained_count >= 0),
  error_code text NULL,
  actor_id text NOT NULL,
  occurred_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS governance_deletion_events_request_idx ON governance_deletion_events (request_id, occurred_at);
CREATE INDEX IF NOT EXISTS governance_deletion_events_subject_idx ON governance_deletion_events (organization_id, subject_user_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS governance_audit_export_jobs (
  job_id text PRIMARY KEY,
  organization_id uuid NULL,
  export_format text NOT NULL CHECK (export_format IN ('JSON','CSV')),
  status text NOT NULL CHECK (status IN ('PENDING','RUNNING','READY','FAILED','EXPIRED')),
  query_snapshot jsonb NOT NULL CHECK (jsonb_typeof(query_snapshot) = 'object'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL,
  completed_at timestamptz NULL,
  object_ref text NULL,
  file_name text NULL,
  checksum_sha256 char(64) NULL,
  size_bytes bigint NULL CHECK (size_bytes IS NULL OR size_bytes >= 0),
  error_code text NULL,
  CHECK ((status IN ('READY','EXPIRED')) = (object_ref IS NOT NULL AND file_name IS NOT NULL AND checksum_sha256 IS NOT NULL AND size_bytes IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS governance_audit_export_jobs_org_idx ON governance_audit_export_jobs (organization_id, created_at DESC);

CREATE OR REPLACE FUNCTION governance_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'GOVERNANCE_APPEND_ONLY';
END;
$$;

DROP TRIGGER IF EXISTS governance_retention_policies_append_only ON governance_retention_policies;
CREATE TRIGGER governance_retention_policies_append_only
BEFORE UPDATE OR DELETE ON governance_retention_policies
FOR EACH ROW EXECUTE FUNCTION governance_reject_mutation();

DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION governance_reject_mutation();

DROP TRIGGER IF EXISTS governance_legal_hold_events_append_only ON governance_legal_hold_events;
CREATE TRIGGER governance_legal_hold_events_append_only
BEFORE UPDATE OR DELETE ON governance_legal_hold_events
FOR EACH ROW EXECUTE FUNCTION governance_reject_mutation();

DROP TRIGGER IF EXISTS governance_deletion_events_append_only ON governance_deletion_events;
CREATE TRIGGER governance_deletion_events_append_only
BEFORE UPDATE OR DELETE ON governance_deletion_events
FOR EACH ROW EXECUTE FUNCTION governance_reject_mutation();

REVOKE UPDATE, DELETE ON governance_retention_policies FROM PUBLIC;
REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC;
REVOKE UPDATE, DELETE ON governance_legal_hold_events FROM PUBLIC;
REVOKE UPDATE, DELETE ON governance_deletion_events FROM PUBLIC;

COMMIT;
