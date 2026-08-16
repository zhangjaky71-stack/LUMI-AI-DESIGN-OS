ALTER TABLE projects
ADD COLUMN brief_version INTEGER DEFAULT 1 NOT NULL;

-- statement-breakpoint

ALTER TABLE projects
ADD COLUMN archived_at TIMESTAMP WITH TIME ZONE;

-- statement-breakpoint

ALTER TABLE projects
ADD CONSTRAINT ck_projects_brief_version_positive CHECK (brief_version > 0);

-- statement-breakpoint

ALTER TABLE projects
ADD CONSTRAINT ck_projects_archive_timestamp_consistency CHECK (
  (status = 'archived' AND archived_at IS NOT NULL) OR
  (status <> 'archived' AND archived_at IS NULL)
) NOT VALID;

-- statement-breakpoint

UPDATE projects SET archived_at = COALESCE(deleted_at, updated_at, now()) WHERE status = 'archived';

-- statement-breakpoint

ALTER TABLE projects VALIDATE CONSTRAINT ck_projects_archive_timestamp_consistency;

-- statement-breakpoint

CREATE TABLE project_brief_versions (
  id UUID NOT NULL,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  version_number INTEGER NOT NULL,
  brief_json JSONB NOT NULL,
  changed_by UUID,
  change_reason VARCHAR(1000),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT pk_project_brief_versions PRIMARY KEY (id),
  CONSTRAINT uq_project_brief_version UNIQUE (project_id, version_number),
  CONSTRAINT ck_project_brief_versions_version_number_positive CHECK (version_number > 0),
  CONSTRAINT fk_project_brief_versions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_project_brief_versions_project_id_projects FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
  CONSTRAINT fk_project_brief_versions_changed_by_users FOREIGN KEY (changed_by) REFERENCES users(id) ON DELETE SET NULL
);

-- statement-breakpoint

INSERT INTO project_brief_versions (
  id, organization_id, project_id, version_number, brief_json, changed_by, change_reason, created_at
)
SELECT gen_random_uuid(), organization_id, id, 1, brief_json, created_by, 'migrated baseline brief', created_at
FROM projects
ON CONFLICT (project_id, version_number) DO NOTHING;

-- statement-breakpoint

CREATE INDEX ix_project_brief_versions_org_project_version
ON project_brief_versions (organization_id, project_id, version_number DESC);

-- statement-breakpoint

CREATE TABLE project_branch_defaults (
  id UUID NOT NULL,
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  name VARCHAR(120) DEFAULT 'main' NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT pk_project_branch_defaults PRIMARY KEY (id),
  CONSTRAINT uq_project_branch_defaults_project UNIQUE (project_id),
  CONSTRAINT fk_project_branch_defaults_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_project_branch_defaults_project_id_projects FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- statement-breakpoint

INSERT INTO project_branch_defaults (id, organization_id, project_id, name, created_at)
SELECT gen_random_uuid(), organization_id, id, 'main', created_at FROM projects
ON CONFLICT (project_id) DO NOTHING;

-- statement-breakpoint

CREATE TABLE project_summaries (
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  latest_artifact_preview_id UUID,
  last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  active_run_count INTEGER DEFAULT 0 NOT NULL,
  artifact_count INTEGER DEFAULT 0 NOT NULL,
  projection_version INTEGER DEFAULT 1 NOT NULL,
  CONSTRAINT pk_project_summaries PRIMARY KEY (project_id),
  CONSTRAINT ck_project_summaries_active_run_count_nonnegative CHECK (active_run_count >= 0),
  CONSTRAINT ck_project_summaries_artifact_count_nonnegative CHECK (artifact_count >= 0),
  CONSTRAINT ck_project_summaries_projection_version_positive CHECK (projection_version > 0),
  CONSTRAINT fk_project_summaries_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_project_summaries_project_id_projects FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- statement-breakpoint

INSERT INTO project_summaries (organization_id, project_id, last_activity_at, active_run_count, artifact_count)
SELECT
  p.organization_id,
  p.id,
  p.updated_at,
  (SELECT count(*) FROM agent_runs r WHERE r.project_id = p.id AND r.status IN ('pending','running','waiting_user','cancel_requested','paused')),
  (SELECT count(*) FROM artifacts a WHERE a.project_id = p.id)
FROM projects p
ON CONFLICT (project_id) DO NOTHING;

-- statement-breakpoint

CREATE INDEX ix_projects_org_updated ON projects (organization_id, updated_at DESC, id DESC);

-- statement-breakpoint

CREATE INDEX ix_projects_workspace_updated ON projects (workspace_id, updated_at DESC, id DESC);

-- statement-breakpoint

CREATE INDEX ix_projects_org_name_lower ON projects (organization_id, lower(name));

-- statement-breakpoint

ALTER TABLE project_brief_versions ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_project_brief_versions ON project_brief_versions
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE project_branch_defaults ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_project_branch_defaults ON project_branch_defaults
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE project_summaries ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_project_summaries ON project_summaries
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE project_brief_versions, project_branch_defaults TO lumi_app;
    GRANT SELECT, INSERT, UPDATE ON TABLE project_summaries TO lumi_app;
  END IF;
END;
$$;
