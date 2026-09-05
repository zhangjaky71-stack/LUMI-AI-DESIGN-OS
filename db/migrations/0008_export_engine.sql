BEGIN;

CREATE TABLE IF NOT EXISTS export_jobs (
  organization_id uuid NOT NULL,
  id text NOT NULL,
  project_id uuid NOT NULL,
  operation_id text NOT NULL,
  export_fingerprint char(64) NOT NULL CHECK (export_fingerprint ~ '^[0-9a-f]{64}$'),
  artifact_version_id uuid NOT NULL,
  design_document_version_id text NOT NULL CHECK (design_document_version_id <> ''),
  source_content_hash char(64) NOT NULL CHECK (source_content_hash ~ '^[0-9a-f]{64}$'),
  constraint_snapshot_hash char(64) NOT NULL CHECK (constraint_snapshot_hash ~ '^[0-9a-f]{64}$'),
  compiler_version text NOT NULL,
  compiler_compile_hash char(64) NOT NULL CHECK (compiler_compile_hash ~ '^[0-9a-f]{64}$'),
  source_snapshot jsonb NOT NULL,
  export_spec jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING','RENDERING','PACKAGING','VALIDATING','READY','FAILED','EXPIRED')),
  progress smallint NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  requested_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  error_code text NULL,
  PRIMARY KEY (organization_id, id),
  UNIQUE (organization_id, operation_id),
  FOREIGN KEY (organization_id, artifact_version_id) REFERENCES artifact_versions(organization_id, id)
);

CREATE INDEX IF NOT EXISTS export_jobs_ready_fingerprint_idx
  ON export_jobs (organization_id, export_fingerprint, expires_at DESC)
  WHERE status = 'READY';

CREATE INDEX IF NOT EXISTS export_jobs_expiry_idx
  ON export_jobs (status, expires_at)
  WHERE status IN ('READY','FAILED');

CREATE TABLE IF NOT EXISTS export_files (
  organization_id uuid NOT NULL,
  id text NOT NULL,
  export_job_id text NOT NULL,
  variant_id text NOT NULL,
  role text NOT NULL CHECK (role IN ('OUTPUT','MANIFEST','PACKAGE')),
  storage_key text NOT NULL CHECK (storage_key <> '' AND storage_key NOT LIKE '%://%' AND storage_key NOT LIKE '%..%'),
  filename text NOT NULL CHECK (filename <> ''),
  mime_type text NOT NULL,
  checksum_sha256 char(64) NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes bigint NOT NULL CHECK (size_bytes > 0),
  width integer NULL CHECK (width IS NULL OR width > 0),
  height integer NULL CHECK (height IS NULL OR height > 0),
  page_count integer NULL CHECK (page_count IS NULL OR page_count > 0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, id),
  UNIQUE (organization_id, export_job_id, variant_id, role),
  FOREIGN KEY (organization_id, export_job_id) REFERENCES export_jobs(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS export_files_job_idx
  ON export_files (organization_id, export_job_id, created_at);

CREATE TABLE IF NOT EXISTS export_format_validations (
  organization_id uuid NOT NULL,
  export_job_id text NOT NULL,
  export_file_id text NOT NULL,
  validator text NOT NULL,
  status text NOT NULL CHECK (status IN ('PASS','FAIL')),
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  validated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, export_file_id, validator),
  FOREIGN KEY (organization_id, export_job_id) REFERENCES export_jobs(organization_id, id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, export_file_id) REFERENCES export_files(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS export_download_audit (
  organization_id uuid NOT NULL,
  export_job_id text NOT NULL,
  export_file_id text NOT NULL,
  actor_id text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('ALLOWED','DENIED')),
  signed_ttl_seconds integer NULL CHECK (signed_ttl_seconds IS NULL OR signed_ttl_seconds BETWEEN 30 AND 900),
  requested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, export_job_id, export_file_id, actor_id, requested_at),
  FOREIGN KEY (organization_id, export_job_id) REFERENCES export_jobs(organization_id, id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, export_file_id) REFERENCES export_files(organization_id, id) ON DELETE CASCADE
);

-- Signed URLs are deliberately absent from durable schema. Download URLs are generated
-- only after authorization and expire at the signer boundary.
-- source_snapshot must contain exact immutable Design IR/render-plan identity with all
-- ephemeral compiler URI/URL fields stripped by NODE-49 application validation.

COMMIT;
