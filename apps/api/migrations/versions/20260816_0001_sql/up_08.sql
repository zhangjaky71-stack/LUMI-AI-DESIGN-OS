ALTER TABLE idempotency_operations ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_idempotency_operations ON idempotency_operations
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE inbox_events ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_inbox_events ON inbox_events
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_organization_members ON organization_members
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_outbox_events ON outbox_events
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_project_members ON project_members
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_projects ON projects
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE provider_requests ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_provider_requests ON provider_requests
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE task_dependencies ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_task_dependencies ON task_dependencies
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_tasks ON tasks
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE usage_counters ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_usage_counters ON usage_counters
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_workspace_members ON workspace_members
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_workspaces ON workspaces
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE agent_run_steps, agent_runs, approvals, artifact_branches, artifact_edges, artifact_files, artifact_provenance, artifact_versions, artifacts, asset_embeddings, asset_files, asset_metadata, asset_previews, asset_rights, assets, audit_events, auth_identities, brand_fonts, brand_logos, brand_palettes, brand_rules, brands, cost_ledger, design_document_versions, design_documents, generations, idempotency_operations, inbox_events, organization_members, organizations, outbox_events, project_members, projects, provider_requests, task_dependencies, tasks, usage_counters, users, workspace_members, workspaces TO lumi_app;
    REVOKE UPDATE, DELETE ON TABLE cost_ledger, audit_events, inbox_events,
      design_document_versions, artifact_provenance FROM lumi_app;
  END IF;
END;
$$;
