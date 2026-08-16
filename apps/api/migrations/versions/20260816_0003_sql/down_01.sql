DROP POLICY IF EXISTS tenant_isolation_agent_run_project_context ON agent_run_project_context;

-- statement-breakpoint

DROP TABLE IF EXISTS agent_run_project_context;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_project_summaries ON project_summaries;

-- statement-breakpoint

DROP TABLE IF EXISTS project_summaries;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_project_branch_defaults ON project_branch_defaults;

-- statement-breakpoint

DROP TABLE IF EXISTS project_branch_defaults;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_project_brief_versions ON project_brief_versions;

-- statement-breakpoint

DROP TABLE IF EXISTS project_brief_versions;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_projects_org_name_lower;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_projects_workspace_updated;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_projects_org_updated;

-- statement-breakpoint

ALTER TABLE projects DROP CONSTRAINT IF EXISTS ck_projects_archive_timestamp_consistency;

-- statement-breakpoint

ALTER TABLE projects DROP CONSTRAINT IF EXISTS ck_projects_brief_version_positive;

-- statement-breakpoint

ALTER TABLE projects DROP COLUMN IF EXISTS archived_at;

-- statement-breakpoint

ALTER TABLE projects DROP COLUMN IF EXISTS brief_version;
