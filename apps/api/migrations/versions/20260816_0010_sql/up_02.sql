CREATE TRIGGER trg_agent_graph_definitions_updated_at
BEFORE UPDATE ON agent_graph_definitions
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_agent_run_control_updated_at
BEFORE UPDATE ON agent_run_control
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_agent_run_control_same_tenant
BEFORE INSERT OR UPDATE ON agent_run_control
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk(
  'agent_run_id', 'agent_runs',
  'project_id', 'projects',
  'task_id', 'tasks'
);

-- statement-breakpoint

ALTER TABLE agent_run_control ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_agent_run_control ON agent_run_control
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

GRANT SELECT ON agent_graph_definitions TO lumi_app;

-- statement-breakpoint

REVOKE INSERT, UPDATE, DELETE ON agent_graph_definitions FROM lumi_app;

-- statement-breakpoint

GRANT SELECT, INSERT, UPDATE ON agent_run_control TO lumi_app;

-- statement-breakpoint

REVOKE DELETE ON agent_run_control FROM lumi_app;
