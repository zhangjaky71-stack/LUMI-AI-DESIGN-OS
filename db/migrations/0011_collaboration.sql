BEGIN;

-- Durable collaboration truth. Presence/cursor/selection awareness is intentionally absent:
-- it belongs to the ephemeral realtime store and must never become Design IR history.
CREATE TABLE IF NOT EXISTS collaboration_threads (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  artifact_version_id uuid NULL,
  design_document_version_id text NOT NULL CHECK (design_document_version_id <> '' AND lower(design_document_version_id) NOT IN ('latest','head','current')),
  node_id text NULL,
  frame_id text NULL,
  anchor jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL CHECK (status IN ('OPEN','RESOLVED','REOPENED')),
  created_by_type text NOT NULL CHECK (created_by_type IN ('USER','AGENT')),
  created_by_id text NOT NULL,
  created_by_agent_run_id text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz NULL,
  UNIQUE (organization_id, project_id, id),
  CHECK ((created_by_type = 'AGENT' AND created_by_agent_run_id IS NOT NULL) OR (created_by_type = 'USER' AND created_by_agent_run_id IS NULL)),
  FOREIGN KEY (organization_id, artifact_version_id) REFERENCES artifact_versions(organization_id, id)
);

CREATE INDEX IF NOT EXISTS collaboration_threads_project_idx
  ON collaboration_threads (organization_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS collaboration_threads_version_idx
  ON collaboration_threads (organization_id, artifact_version_id, design_document_version_id);

CREATE TABLE IF NOT EXISTS collaboration_comments (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  thread_id uuid NOT NULL,
  actor_type text NOT NULL CHECK (actor_type IN ('USER','AGENT')),
  actor_id text NOT NULL,
  actor_agent_run_id text NULL,
  body text NOT NULL CHECK (length(body) <= 4000),
  mention_actor_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  edited_at timestamptz NULL,
  deleted_at timestamptz NULL,
  CHECK (jsonb_typeof(mention_actor_ids) = 'array'),
  CHECK ((actor_type = 'AGENT' AND actor_agent_run_id IS NOT NULL) OR (actor_type = 'USER' AND actor_agent_run_id IS NULL)),
  FOREIGN KEY (organization_id, project_id, thread_id)
    REFERENCES collaboration_threads(organization_id, project_id, id)
);

CREATE INDEX IF NOT EXISTS collaboration_comments_thread_idx
  ON collaboration_comments (organization_id, project_id, thread_id, created_at);

CREATE TABLE IF NOT EXISTS collaboration_operation_commits (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  document_id text NOT NULL,
  operation_id text NOT NULL,
  base_version_id text NOT NULL CHECK (lower(base_version_id) NOT IN ('latest','head','current')),
  result_version_id text NOT NULL CHECK (lower(result_version_id) NOT IN ('latest','head','current')),
  node_id text NOT NULL,
  property_name text NOT NULL,
  actor_type text NOT NULL CHECK (actor_type IN ('USER','AGENT')),
  actor_id text NOT NULL,
  actor_agent_run_id text NULL,
  operation_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, project_id, document_id, operation_id),
  CHECK ((actor_type = 'AGENT' AND actor_agent_run_id IS NOT NULL) OR (actor_type = 'USER' AND actor_agent_run_id IS NULL))
);

CREATE INDEX IF NOT EXISTS collaboration_operation_version_idx
  ON collaboration_operation_commits (organization_id, project_id, document_id, result_version_id, created_at);

CREATE TABLE IF NOT EXISTS collaboration_audit_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  event_type text NOT NULL,
  target_id text NOT NULL,
  actor_type text NOT NULL CHECK (actor_type IN ('USER','AGENT')),
  actor_id text NOT NULL,
  actor_agent_run_id text NULL,
  safe_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((actor_type = 'AGENT' AND actor_agent_run_id IS NOT NULL) OR (actor_type = 'USER' AND actor_agent_run_id IS NULL))
);

CREATE INDEX IF NOT EXISTS collaboration_audit_project_idx
  ON collaboration_audit_events (organization_id, project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS collaboration_notifications (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  recipient_actor_id text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('MENTION','COMMENT_REPLY','APPROVAL_REQUEST','ARTIFACT_READY')),
  thread_id uuid NULL,
  safe_summary text NOT NULL CHECK (length(safe_summary) <= 500),
  created_at timestamptz NOT NULL DEFAULT now(),
  read_at timestamptz NULL,
  FOREIGN KEY (organization_id, project_id, thread_id)
    REFERENCES collaboration_threads(organization_id, project_id, id)
);

CREATE INDEX IF NOT EXISTS collaboration_notifications_recipient_idx
  ON collaboration_notifications (organization_id, recipient_actor_id, read_at, created_at DESC);

COMMIT;
