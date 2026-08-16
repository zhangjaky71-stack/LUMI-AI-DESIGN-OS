ALTER TABLE asset_upload_sessions ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_asset_upload_sessions ON asset_upload_sessions
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

ALTER TABLE asset_validation_reports ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_asset_validation_reports ON asset_validation_reports
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_asset_storage_same_tenant_guard()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  asset_org UUID;
  asset_project UUID;
  upload_org UUID;
  upload_asset UUID;
  expected_key TEXT;
BEGIN
  IF TG_TABLE_NAME = 'asset_upload_sessions' THEN
    SELECT organization_id, project_id INTO asset_org, asset_project FROM assets WHERE id = NEW.asset_id;
    IF asset_org IS DISTINCT FROM NEW.organization_id OR asset_project IS DISTINCT FROM NEW.project_id THEN
      RAISE EXCEPTION 'asset upload tenant/project mismatch' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM projects p WHERE p.id = NEW.project_id AND p.organization_id = NEW.organization_id
    ) THEN
      RAISE EXCEPTION 'asset upload project tenant mismatch' USING ERRCODE = '23514';
    END IF;
    expected_key := format(
      'org/%s/project/%s/asset/%s/original/%s',
      NEW.organization_id, NEW.project_id, NEW.asset_id, NEW.file_id
    );
    IF NEW.object_key <> expected_key THEN
      RAISE EXCEPTION 'asset object key violates canonical tenant prefix' USING ERRCODE = '23514';
    END IF;
  ELSIF TG_TABLE_NAME = 'asset_validation_reports' THEN
    SELECT organization_id INTO asset_org FROM assets WHERE id = NEW.asset_id;
    SELECT organization_id, asset_id INTO upload_org, upload_asset
      FROM asset_upload_sessions WHERE id = NEW.upload_session_id;
    IF asset_org IS DISTINCT FROM NEW.organization_id
       OR upload_org IS DISTINCT FROM NEW.organization_id
       OR upload_asset IS DISTINCT FROM NEW.asset_id THEN
      RAISE EXCEPTION 'asset validation tenant mismatch' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_asset_upload_sessions_same_tenant
BEFORE INSERT OR UPDATE ON asset_upload_sessions
FOR EACH ROW EXECUTE FUNCTION lumi_asset_storage_same_tenant_guard();

-- statement-breakpoint

CREATE TRIGGER trg_asset_validation_reports_same_tenant
BEFORE INSERT ON asset_validation_reports
FOR EACH ROW EXECUTE FUNCTION lumi_asset_storage_same_tenant_guard();

-- statement-breakpoint

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app') THEN
    GRANT SELECT, INSERT, UPDATE ON TABLE asset_upload_sessions TO lumi_app;
    GRANT SELECT, INSERT ON TABLE asset_validation_reports TO lumi_app;
    REVOKE DELETE ON TABLE asset_upload_sessions FROM lumi_app;
    REVOKE UPDATE, DELETE ON TABLE asset_validation_reports FROM lumi_app;
  END IF;
END;
$$;
