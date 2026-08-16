CREATE OR REPLACE FUNCTION lumi_queue_runtime_same_tenant_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  target_org UUID;
BEGIN
  SELECT organization_id INTO target_org FROM projects WHERE id = NEW.project_id;
  IF target_org IS NULL OR target_org <> NEW.organization_id THEN
    RAISE EXCEPTION 'runtime job project unavailable in tenant'
      USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_runtime_jobs_same_tenant
BEFORE INSERT OR UPDATE OF organization_id, project_id ON runtime_jobs
FOR EACH ROW EXECUTE FUNCTION lumi_queue_runtime_same_tenant_guard();

-- statement-breakpoint

ALTER TABLE runtime_jobs ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_runtime_jobs ON runtime_jobs
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE dead_letter_records ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_dead_letter_records ON dead_letter_records
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app') THEN
    GRANT SELECT, INSERT, UPDATE ON TABLE runtime_jobs, dead_letter_records TO lumi_app;
    REVOKE DELETE ON TABLE runtime_jobs, dead_letter_records FROM lumi_app;
  END IF;
END;
$$;
