BEGIN;

CREATE TABLE IF NOT EXISTS approvals (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  agent_run_id text NULL,
  task_id text NULL,
  approval_type text NOT NULL CHECK (approval_type IN (
    'CREATIVE_DIRECTION','ARTIFACT_VERSION','BRAND_RULE_SET','BUDGET_INCREASE',
    'EXTERNAL_PUBLISH','DESTRUCTIVE_ACTION','CUSTOM_REVIEW'
  )),
  subject_type text NOT NULL CHECK (subject_type <> ''),
  subject_id text NOT NULL CHECK (subject_id <> ''),
  subject_version text NOT NULL CHECK (subject_version <> '' AND lower(subject_version) NOT IN ('latest','head','current')),
  status text NOT NULL CHECK (status IN ('PENDING','APPROVED','REJECTED','CHANGES_REQUESTED','EXPIRED','CANCELLED','SUPERSEDED')),
  requested_by text NOT NULL,
  required_permission text NOT NULL CHECK (required_permission <> ''),
  required_roles jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(required_roles) = 'array'),
  policy_mode text NOT NULL CHECK (policy_mode IN ('ANY_ONE','ALL','MIN_N','ROLE_BASED_SEQUENCE')),
  policy_version integer NOT NULL CHECK (policy_version >= 1),
  min_approvals integer NOT NULL DEFAULT 1 CHECK (min_approvals >= 1),
  sequence_roles jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(sequence_roles) = 'array'),
  payload_summary text NOT NULL CHECK (length(payload_summary) BETWEEN 1 AND 1000),
  expires_at timestamptz NULL,
  resolved_at timestamptz NULL,
  resolved_by text NULL,
  superseded_by uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, project_id, id),
  FOREIGN KEY (organization_id, project_id, superseded_by)
    REFERENCES approvals(organization_id, project_id, id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS approvals_project_status_idx ON approvals (organization_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS approvals_subject_idx ON approvals (organization_id, project_id, subject_type, subject_id, subject_version);
CREATE INDEX IF NOT EXISTS approvals_run_idx ON approvals (organization_id, project_id, agent_run_id) WHERE agent_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS approval_decisions (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  approval_id uuid NOT NULL,
  actor_id text NOT NULL,
  actor_roles jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(actor_roles) = 'array'),
  decision text NOT NULL CHECK (decision IN ('APPROVE','REJECT','REQUEST_CHANGES')),
  reason text NULL CHECK (reason IS NULL OR length(reason) <= 1000),
  decided_subject_version text NOT NULL CHECK (decided_subject_version <> '' AND lower(decided_subject_version) NOT IN ('latest','head','current')),
  idempotency_key text NOT NULL CHECK (idempotency_key <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, project_id, id),
  UNIQUE (organization_id, idempotency_key),
  FOREIGN KEY (organization_id, project_id, approval_id) REFERENCES approvals(organization_id, project_id, id)
);

CREATE INDEX IF NOT EXISTS approval_decisions_approval_idx ON approval_decisions (organization_id, project_id, approval_id, created_at);

CREATE TABLE IF NOT EXISTS approval_change_requests (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  approval_id uuid NOT NULL,
  decision_id uuid NOT NULL,
  comment text NOT NULL DEFAULT '' CHECK (length(comment) <= 4000),
  node_refs jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(node_refs) = 'array'),
  region_refs jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(region_refs) = 'array'),
  requested_changes jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(requested_changes) = 'array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, project_id, approval_id),
  FOREIGN KEY (organization_id, project_id, approval_id) REFERENCES approvals(organization_id, project_id, id),
  FOREIGN KEY (organization_id, project_id, decision_id) REFERENCES approval_decisions(organization_id, project_id, id),
  CHECK (comment <> '' OR jsonb_array_length(requested_changes) > 0)
);

CREATE TABLE IF NOT EXISTS approval_audit_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  approval_id uuid NOT NULL,
  event_type text NOT NULL,
  actor_id text NOT NULL,
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  subject_version text NOT NULL CHECK (subject_version <> '' AND lower(subject_version) NOT IN ('latest','head','current')),
  safe_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (organization_id, project_id, approval_id) REFERENCES approvals(organization_id, project_id, id)
);

CREATE INDEX IF NOT EXISTS approval_audit_project_idx ON approval_audit_events (organization_id, project_id, created_at DESC);

-- Approval-required in-app notifications reuse NODE-61 collaboration_notifications. This prevents
-- a second notification store; production wiring adapts ApprovalNotificationPort to that table.

COMMIT;
