CREATE TRIGGER trg_asset_rights_same_tenant
BEFORE INSERT OR UPDATE ON asset_rights
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('asset_id', 'assets');

-- statement-breakpoint

CREATE TRIGGER trg_design_documents_same_tenant
BEFORE INSERT OR UPDATE ON design_documents
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects');

-- statement-breakpoint

CREATE TRIGGER trg_design_document_versions_same_tenant
BEFORE INSERT OR UPDATE ON design_document_versions
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('design_document_id', 'design_documents');

-- statement-breakpoint

CREATE TRIGGER trg_artifacts_same_tenant
BEFORE INSERT OR UPDATE ON artifacts
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects', 'design_document_id', 'design_documents');

-- statement-breakpoint

CREATE TRIGGER trg_artifact_branches_same_tenant
BEFORE INSERT OR UPDATE ON artifact_branches
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects', 'artifact_id', 'artifacts', 'head_version_id', 'artifact_versions');

-- statement-breakpoint

CREATE TRIGGER trg_artifact_versions_same_tenant
BEFORE INSERT OR UPDATE ON artifact_versions
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('artifact_id', 'artifacts', 'branch_id', 'artifact_branches');

-- statement-breakpoint

CREATE TRIGGER trg_artifact_edges_same_tenant
BEFORE INSERT OR UPDATE ON artifact_edges
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('from_artifact_version_id', 'artifact_versions', 'to_artifact_version_id', 'artifact_versions');

-- statement-breakpoint

CREATE TRIGGER trg_artifact_files_same_tenant
BEFORE INSERT OR UPDATE ON artifact_files
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('artifact_version_id', 'artifact_versions');

-- statement-breakpoint

CREATE TRIGGER trg_artifact_provenance_same_tenant
BEFORE INSERT OR UPDATE ON artifact_provenance
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('artifact_version_id', 'artifact_versions');

-- statement-breakpoint

CREATE TRIGGER trg_agent_runs_same_tenant
BEFORE INSERT OR UPDATE ON agent_runs
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects');

-- statement-breakpoint

CREATE TRIGGER trg_agent_run_steps_same_tenant
BEFORE INSERT OR UPDATE ON agent_run_steps
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('agent_run_id', 'agent_runs');

-- statement-breakpoint

CREATE TRIGGER trg_tasks_same_tenant
BEFORE INSERT OR UPDATE ON tasks
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects', 'parent_task_id', 'tasks');

-- statement-breakpoint

CREATE TRIGGER trg_task_dependencies_same_tenant
BEFORE INSERT OR UPDATE ON task_dependencies
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('task_id', 'tasks', 'depends_on_task_id', 'tasks');

-- statement-breakpoint

CREATE TRIGGER trg_approvals_same_tenant
BEFORE INSERT OR UPDATE ON approvals
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects');

-- statement-breakpoint

CREATE TRIGGER trg_generations_same_tenant
BEFORE INSERT OR UPDATE ON generations
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects', 'operation_id', 'idempotency_operations', 'agent_run_id', 'agent_runs');

-- statement-breakpoint

CREATE TRIGGER trg_provider_requests_same_tenant
BEFORE INSERT OR UPDATE ON provider_requests
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('generation_id', 'generations');

-- statement-breakpoint

CREATE TRIGGER trg_cost_ledger_same_tenant
BEFORE INSERT OR UPDATE ON cost_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects', 'task_id', 'tasks', 'agent_run_id', 'agent_runs', 'generation_id', 'generations', 'related_entry_id', 'cost_ledger', 'provider_request_id', 'provider_requests');

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_current_organization_id() RETURNS uuid AS $$
  SELECT NULLIF(current_setting('app.current_organization_id', true), '')::uuid;
$$ LANGUAGE sql STABLE;

-- statement-breakpoint

ALTER TABLE agent_run_steps ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_agent_run_steps ON agent_run_steps
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_agent_runs ON agent_runs
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_approvals ON approvals
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE artifact_branches ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_artifact_branches ON artifact_branches
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE artifact_edges ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_artifact_edges ON artifact_edges
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE artifact_files ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_artifact_files ON artifact_files
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE artifact_provenance ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_artifact_provenance ON artifact_provenance
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE artifact_versions ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_artifact_versions ON artifact_versions
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());
