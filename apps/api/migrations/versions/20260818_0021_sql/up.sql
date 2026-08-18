CREATE TABLE comment_threads (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  artifact_id UUID NOT NULL REFERENCES artifacts(id) ON DELETE RESTRICT,
  artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  design_node_id UUID,
  x NUMERIC(20,6),
  y NUMERIC(20,6),
  status VARCHAR(24) NOT NULL DEFAULT 'OPEN',
  needs_reanchor BOOLEAN NOT NULL DEFAULT FALSE,
  created_by VARCHAR(200) NOT NULL,
  resolved_by VARCHAR(200),
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_comment_threads_status CHECK (status IN ('OPEN','RESOLVED')),
  CONSTRAINT ck_comment_threads_resolution CHECK (
    (status = 'RESOLVED' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL)
    OR (status = 'OPEN' AND resolved_by IS NULL AND resolved_at IS NULL)
  ),
  CONSTRAINT ck_comment_threads_anchor_pair CHECK ((x IS NULL) = (y IS NULL))
);

-- statement-breakpoint

CREATE INDEX ix_comment_threads_version
ON comment_threads (organization_id, project_id, artifact_version_id, status, created_at);

-- statement-breakpoint

CREATE INDEX ix_comment_threads_artifact
ON comment_threads (organization_id, artifact_id, created_at);

-- statement-breakpoint

CREATE TABLE comments (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  thread_id UUID NOT NULL REFERENCES comment_threads(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  mentions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_by VARCHAR(200) NOT NULL,
  edited_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  revision INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_comments_revision CHECK (revision >= 1),
  CONSTRAINT ck_comments_body_length CHECK (length(body) <= 20000)
);

-- statement-breakpoint

CREATE INDEX ix_comments_thread_created
ON comments (organization_id, thread_id, created_at);

-- statement-breakpoint

CREATE TABLE comment_revisions (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  comment_id UUID NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
  revision_number INTEGER NOT NULL,
  action VARCHAR(24) NOT NULL,
  body_snapshot TEXT NOT NULL,
  mentions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  actor_id VARCHAR(200) NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_comment_revision_number UNIQUE (comment_id, revision_number),
  CONSTRAINT ck_comment_revisions_revision CHECK (revision_number >= 1),
  CONSTRAINT ck_comment_revisions_action CHECK (action IN ('CREATED','EDITED','DELETED')),
  CONSTRAINT ck_comment_revisions_body_length CHECK (length(body_snapshot) <= 20000)
);

-- statement-breakpoint

CREATE INDEX ix_comment_revisions_comment
ON comment_revisions (organization_id, comment_id, revision_number);
