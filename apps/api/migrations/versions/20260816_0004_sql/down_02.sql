DROP TRIGGER IF EXISTS trg_asset_validation_reports_same_tenant ON asset_validation_reports;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_asset_upload_sessions_same_tenant ON asset_upload_sessions;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_asset_storage_same_tenant_guard();

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_asset_validation_reports ON asset_validation_reports;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_asset_upload_sessions ON asset_upload_sessions;
