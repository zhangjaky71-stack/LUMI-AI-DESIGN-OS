DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app') THEN
    REVOKE UPDATE, DELETE ON TABLE project_brief_versions FROM lumi_app;
    REVOKE DELETE ON TABLE project_branch_defaults FROM lumi_app;
  END IF;
END;
$$;

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_require_project_accepts_paid_command()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  project_status VARCHAR(32);
BEGIN
  SELECT status INTO project_status
  FROM projects
  WHERE id = NEW.project_id AND organization_id = NEW.organization_id;

  IF project_status IS NULL THEN
    RAISE EXCEPTION 'project unavailable for paid command'
      USING ERRCODE = '23503';
  END IF;

  IF project_status IN ('paused', 'archived') THEN
    RAISE EXCEPTION 'project status % blocks new paid command', project_status
      USING ERRCODE = '55000';
  END IF;

  RETURN NEW;
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_agent_runs_project_paid_command_guard
BEFORE INSERT ON agent_runs
FOR EACH ROW EXECUTE FUNCTION lumi_require_project_accepts_paid_command();

-- statement-breakpoint

CREATE TRIGGER trg_generations_project_paid_command_guard
BEFORE INSERT ON generations
FOR EACH ROW EXECUTE FUNCTION lumi_require_project_accepts_paid_command();
