CREATE OR REPLACE FUNCTION lumi_project_core_same_tenant_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  project_org UUID;
  run_org UUID;
BEGIN
  SELECT organization_id INTO project_org FROM projects WHERE id = NEW.project_id;
  IF project_org IS NULL OR project_org <> NEW.organization_id THEN
    RAISE EXCEPTION 'project core cross-tenant project reference rejected'
      USING ERRCODE = '23514';
  END IF;

  IF TG_TABLE_NAME = 'agent_run_project_context' THEN
    SELECT organization_id INTO run_org FROM agent_runs WHERE id = NEW.agent_run_id;
    IF run_org IS NULL OR run_org <> NEW.organization_id THEN
      RAISE EXCEPTION 'project core cross-tenant agent run reference rejected'
        USING ERRCODE = '23514';
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_project_brief_versions_same_tenant
BEFORE INSERT OR UPDATE ON project_brief_versions
FOR EACH ROW EXECUTE FUNCTION lumi_project_core_same_tenant_guard();

-- statement-breakpoint

CREATE TRIGGER trg_project_branch_defaults_same_tenant
BEFORE INSERT OR UPDATE ON project_branch_defaults
FOR EACH ROW EXECUTE FUNCTION lumi_project_core_same_tenant_guard();

-- statement-breakpoint

CREATE TRIGGER trg_project_summaries_same_tenant
BEFORE INSERT OR UPDATE ON project_summaries
FOR EACH ROW EXECUTE FUNCTION lumi_project_core_same_tenant_guard();

-- statement-breakpoint

CREATE TRIGGER trg_agent_run_project_context_same_tenant
BEFORE INSERT OR UPDATE ON agent_run_project_context
FOR EACH ROW EXECUTE FUNCTION lumi_project_core_same_tenant_guard();
