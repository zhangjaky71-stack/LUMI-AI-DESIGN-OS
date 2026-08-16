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

CREATE OR REPLACE FUNCTION lumi_validate_agent_run_graph_definition() RETURNS trigger AS $$
DECLARE
  expected_hash text;
  expected_sha text;
  is_enabled boolean;
BEGIN
  SELECT content_hash, code_git_sha, enabled
    INTO expected_hash, expected_sha, is_enabled
  FROM agent_graph_definitions
  WHERE graph_key = NEW.graph_key AND graph_version = NEW.graph_version;

  IF expected_hash IS NULL THEN
    RAISE EXCEPTION 'graph definition % @ % is not published', NEW.graph_key, NEW.graph_version
      USING ERRCODE = '23514';
  END IF;
  IF NOT is_enabled THEN
    RAISE EXCEPTION 'graph definition % @ % is disabled', NEW.graph_key, NEW.graph_version
      USING ERRCODE = '23514';
  END IF;
  IF expected_hash <> NEW.graph_definition_hash OR expected_sha <> NEW.code_git_sha THEN
    RAISE EXCEPTION 'graph definition provenance mismatch for % @ %',
      NEW.graph_key, NEW.graph_version
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

-- statement-breakpoint

CREATE TRIGGER trg_agent_run_control_graph_definition
BEFORE INSERT OR UPDATE OF graph_key, graph_version, graph_definition_hash, code_git_sha
ON agent_run_control
FOR EACH ROW EXECUTE FUNCTION lumi_validate_agent_run_graph_definition();

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
