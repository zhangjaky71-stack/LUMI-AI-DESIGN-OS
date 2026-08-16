DROP INDEX IF EXISTS ix_assets_project_status;

-- statement-breakpoint

DROP TABLE IF EXISTS asset_validation_reports;

-- statement-breakpoint

DROP TABLE IF EXISTS asset_upload_sessions;

-- statement-breakpoint

ALTER TABLE asset_rights DROP CONSTRAINT IF EXISTS ck_asset_rights_assertion;

-- statement-breakpoint

ALTER TABLE asset_rights DROP COLUMN IF EXISTS asserted_at;

-- statement-breakpoint

ALTER TABLE asset_rights DROP COLUMN IF EXISTS asserted_by;

-- statement-breakpoint

ALTER TABLE asset_rights DROP COLUMN IF EXISTS assertion;

-- statement-breakpoint

ALTER TABLE asset_previews DROP COLUMN IF EXISTS duration_ms;

-- statement-breakpoint

ALTER TABLE asset_previews DROP COLUMN IF EXISTS height;

-- statement-breakpoint

ALTER TABLE asset_previews DROP COLUMN IF EXISTS width;

-- statement-breakpoint

ALTER TABLE asset_previews DROP COLUMN IF EXISTS byte_size;

-- statement-breakpoint

ALTER TABLE asset_previews DROP COLUMN IF EXISTS mime_type;

-- statement-breakpoint

ALTER TABLE asset_previews DROP COLUMN IF EXISTS source_file_id;

-- statement-breakpoint

ALTER TABLE asset_files DROP CONSTRAINT IF EXISTS ck_asset_files_duration_nonnegative;

-- statement-breakpoint

ALTER TABLE asset_files DROP CONSTRAINT IF EXISTS ck_asset_files_role;

-- statement-breakpoint

ALTER TABLE asset_files DROP COLUMN IF EXISTS verified_at;

-- statement-breakpoint

ALTER TABLE asset_files DROP COLUMN IF EXISTS metadata_json;

-- statement-breakpoint

ALTER TABLE asset_files DROP COLUMN IF EXISTS has_alpha;

-- statement-breakpoint

ALTER TABLE asset_files DROP COLUMN IF EXISTS color_profile;

-- statement-breakpoint

ALTER TABLE asset_files DROP COLUMN IF EXISTS codec;

-- statement-breakpoint

ALTER TABLE asset_files DROP COLUMN IF EXISTS fps;

-- statement-breakpoint

ALTER TABLE asset_files DROP COLUMN IF EXISTS duration_ms;

-- statement-breakpoint

ALTER TABLE asset_files DROP COLUMN IF EXISTS mime_type;

-- statement-breakpoint

ALTER TABLE asset_files DROP COLUMN IF EXISTS role;

-- statement-breakpoint

ALTER TABLE assets DROP CONSTRAINT IF EXISTS ck_assets_media_kind;

-- statement-breakpoint

ALTER TABLE assets DROP CONSTRAINT IF EXISTS ck_assets_status;

-- statement-breakpoint

UPDATE assets SET status = CASE
  WHEN status = 'rejected' THEN 'failed'
  WHEN status IN ('uploading','verifying','scanning') THEN 'pending'
  ELSE status
END;

-- statement-breakpoint

ALTER TABLE assets ADD CONSTRAINT ck_assets_status CHECK (status IN ('pending','ready','failed','deleted'));

-- statement-breakpoint

ALTER TABLE assets DROP COLUMN IF EXISTS created_by;

-- statement-breakpoint

ALTER TABLE assets DROP COLUMN IF EXISTS rejected_reason;

-- statement-breakpoint

ALTER TABLE assets DROP COLUMN IF EXISTS media_kind;

-- statement-breakpoint

ALTER TABLE assets DROP COLUMN IF EXISTS declared_mime_type;

-- statement-breakpoint

ALTER TABLE assets DROP COLUMN IF EXISTS original_filename;
