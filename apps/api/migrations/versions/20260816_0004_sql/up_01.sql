ALTER TABLE assets ADD COLUMN original_filename VARCHAR(255) DEFAULT 'unknown' NOT NULL;

-- statement-breakpoint

ALTER TABLE assets ADD COLUMN declared_mime_type VARCHAR(255) DEFAULT 'application/octet-stream' NOT NULL;

-- statement-breakpoint

UPDATE assets SET declared_mime_type = mime_type WHERE declared_mime_type = 'application/octet-stream';

-- statement-breakpoint

ALTER TABLE assets ADD COLUMN media_kind VARCHAR(32);

-- statement-breakpoint

ALTER TABLE assets ADD COLUMN rejected_reason VARCHAR(1000);

-- statement-breakpoint

ALTER TABLE assets ADD COLUMN created_by UUID REFERENCES users(id) ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE assets DROP CONSTRAINT ck_assets_status;

-- statement-breakpoint

UPDATE assets SET status = 'rejected' WHERE status = 'failed';

-- statement-breakpoint

ALTER TABLE assets ADD CONSTRAINT ck_assets_status CHECK (
  status IN ('pending','uploading','verifying','scanning','ready','rejected','deleted')
);

-- statement-breakpoint

ALTER TABLE assets ADD CONSTRAINT ck_assets_media_kind CHECK (
  media_kind IS NULL OR media_kind IN ('image','vector','document','video','font')
);

-- statement-breakpoint

ALTER TABLE asset_files ADD COLUMN role VARCHAR(32) DEFAULT 'original' NOT NULL;

-- statement-breakpoint

ALTER TABLE asset_files ADD COLUMN mime_type VARCHAR(255) DEFAULT 'application/octet-stream' NOT NULL;

-- statement-breakpoint

UPDATE asset_files f SET mime_type = a.mime_type FROM assets a WHERE a.id = f.asset_id;

-- statement-breakpoint

ALTER TABLE asset_files ADD COLUMN duration_ms BIGINT;

-- statement-breakpoint

ALTER TABLE asset_files ADD COLUMN fps NUMERIC(12,6);

-- statement-breakpoint

ALTER TABLE asset_files ADD COLUMN codec VARCHAR(120);

-- statement-breakpoint

ALTER TABLE asset_files ADD COLUMN color_profile VARCHAR(120);

-- statement-breakpoint

ALTER TABLE asset_files ADD COLUMN has_alpha BOOLEAN;

-- statement-breakpoint

ALTER TABLE asset_files ADD COLUMN metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL;

-- statement-breakpoint

ALTER TABLE asset_files ADD COLUMN verified_at TIMESTAMP WITH TIME ZONE;

-- statement-breakpoint

UPDATE asset_files SET verified_at = created_at WHERE verified_at IS NULL;

-- statement-breakpoint

ALTER TABLE asset_files ALTER COLUMN verified_at SET NOT NULL;

-- statement-breakpoint

ALTER TABLE asset_files ADD CONSTRAINT ck_asset_files_role CHECK (
  role IN ('original','sanitized','thumbnail','medium','poster')
);

-- statement-breakpoint

ALTER TABLE asset_files ADD CONSTRAINT ck_asset_files_duration_nonnegative CHECK (
  duration_ms IS NULL OR duration_ms >= 0
);

-- statement-breakpoint

ALTER TABLE asset_previews ADD COLUMN source_file_id UUID REFERENCES asset_files(id) ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE asset_previews ADD COLUMN mime_type VARCHAR(255);

-- statement-breakpoint

ALTER TABLE asset_previews ADD COLUMN byte_size BIGINT;

-- statement-breakpoint

ALTER TABLE asset_previews ADD COLUMN width INTEGER;

-- statement-breakpoint

ALTER TABLE asset_previews ADD COLUMN height INTEGER;

-- statement-breakpoint

ALTER TABLE asset_previews ADD COLUMN duration_ms BIGINT;

-- statement-breakpoint

ALTER TABLE asset_rights ADD COLUMN assertion VARCHAR(32) DEFAULT 'UNKNOWN' NOT NULL;

-- statement-breakpoint

UPDATE asset_rights SET assertion = CASE
  WHEN rights_level = 'owned' THEN 'USER_OWNED'
  WHEN rights_level = 'licensed' THEN 'LICENSED'
  ELSE 'UNKNOWN'
END;

-- statement-breakpoint

ALTER TABLE asset_rights ADD COLUMN asserted_by UUID REFERENCES users(id) ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE asset_rights ADD COLUMN asserted_at TIMESTAMP WITH TIME ZONE;

-- statement-breakpoint

ALTER TABLE asset_rights ADD CONSTRAINT ck_asset_rights_assertion CHECK (
  assertion IN ('USER_OWNED','LICENSED','UNKNOWN')
);

-- statement-breakpoint

CREATE TABLE asset_upload_sessions (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  file_id UUID NOT NULL,
  bucket VARCHAR(128) NOT NULL,
  object_key TEXT NOT NULL UNIQUE,
  original_filename VARCHAR(255) NOT NULL,
  declared_mime_type VARCHAR(255) NOT NULL,
  expected_size BIGINT NOT NULL CHECK (expected_size > 0),
  expected_checksum_sha256 VARCHAR(64) NOT NULL CHECK (expected_checksum_sha256 ~ '^[0-9a-f]{64}$'),
  mode VARCHAR(32) NOT NULL CHECK (mode IN ('single_put','multipart')),
  status VARCHAR(32) DEFAULT 'pending' NOT NULL CHECK (
    status IN ('pending','uploaded','verifying','completed','rejected','expired','aborted')
  ),
  storage_upload_id TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  completed_at TIMESTAMP WITH TIME ZONE,
  CONSTRAINT ck_asset_upload_sessions_expiry CHECK (expires_at > created_at)
);

-- statement-breakpoint

CREATE INDEX ix_asset_upload_sessions_organization_id ON asset_upload_sessions(organization_id);

-- statement-breakpoint

CREATE INDEX ix_asset_upload_sessions_org_expiry ON asset_upload_sessions(organization_id, expires_at);

-- statement-breakpoint

CREATE TABLE asset_validation_reports (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  upload_session_id UUID NOT NULL REFERENCES asset_upload_sessions(id) ON DELETE CASCADE,
  expected_checksum_sha256 VARCHAR(64) NOT NULL CHECK (expected_checksum_sha256 ~ '^[0-9a-f]{64}$'),
  actual_checksum_sha256 VARCHAR(64) NOT NULL CHECK (actual_checksum_sha256 ~ '^[0-9a-f]{64}$'),
  expected_size BIGINT NOT NULL CHECK (expected_size >= 0),
  actual_size BIGINT NOT NULL CHECK (actual_size >= 0),
  sniffed_mime_type VARCHAR(255) NOT NULL,
  media_kind VARCHAR(32) NOT NULL CHECK (media_kind IN ('image','vector','document','video','font')),
  scan_status VARCHAR(32) NOT NULL CHECK (scan_status IN ('clean','infected','unavailable','error')),
  scan_engine VARCHAR(120) NOT NULL,
  scan_signature VARCHAR(500),
  accepted BOOLEAN NOT NULL,
  reason_codes_json JSONB DEFAULT '[]'::jsonb NOT NULL,
  metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- statement-breakpoint

CREATE INDEX ix_asset_validation_reports_organization_id ON asset_validation_reports(organization_id);

-- statement-breakpoint

CREATE INDEX ix_asset_validation_reports_asset_created ON asset_validation_reports(asset_id, created_at DESC);

-- statement-breakpoint

CREATE INDEX ix_assets_project_status ON assets(project_id, status);
