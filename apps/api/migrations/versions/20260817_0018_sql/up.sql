CREATE TABLE export_specs (
  export_job_id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  requested_by VARCHAR(200) NOT NULL,
  semantic_hash VARCHAR(64) NOT NULL,
  spec_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_export_operation UNIQUE (organization_id, operation_id),
  CONSTRAINT ck_export_semantic_hash CHECK (semantic_hash ~ '^[0-9a-f]{64}$')
);

-- statement-breakpoint

CREATE INDEX ix_export_specs_project
ON export_specs (organization_id, project_id, created_at);

-- statement-breakpoint

CREATE TABLE export_jobs (
  export_job_id UUID PRIMARY KEY REFERENCES export_specs(export_job_id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  status VARCHAR(32) NOT NULL,
  runtime_job_id UUID REFERENCES runtime_jobs(id) ON DELETE SET NULL,
  package_id UUID,
  package_json JSONB,
  manifest_json JSONB,
  job_json JSONB NOT NULL,
  error_code VARCHAR(240),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_export_job_status CHECK (
    status IN ('PLANNED','QUEUED','RENDERING','PACKAGING','READY','FAILED','CANCELLED','EXPIRED')
  )
);

-- statement-breakpoint

CREATE INDEX ix_export_jobs_status
ON export_jobs (organization_id, status, updated_at);

-- statement-breakpoint

CREATE TABLE export_items (
  export_job_id UUID NOT NULL REFERENCES export_specs(export_job_id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  artifact_id UUID NOT NULL REFERENCES artifacts(id) ON DELETE RESTRICT,
  artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  target_format VARCHAR(32) NOT NULL,
  output_name VARCHAR(240) NOT NULL,
  snapshot_hash VARCHAR(64) NOT NULL,
  snapshot_json JSONB NOT NULL,
  PRIMARY KEY (export_job_id, ordinal),
  CONSTRAINT uq_export_item_version UNIQUE (export_job_id, artifact_version_id),
  CONSTRAINT ck_export_item_ordinal CHECK (ordinal >= 0),
  CONSTRAINT ck_export_item_format CHECK (
    target_format IN ('ORIGINAL','PNG','JPEG','MP4','PDF','PPTX')
  ),
  CONSTRAINT ck_export_snapshot_hash CHECK (snapshot_hash ~ '^[0-9a-f]{64}$')
);

-- statement-breakpoint

CREATE INDEX ix_export_items_version
ON export_items (organization_id, artifact_version_id);

-- statement-breakpoint

CREATE TABLE export_outputs (
  export_job_id UUID NOT NULL REFERENCES export_specs(export_job_id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  source_artifact_id UUID NOT NULL REFERENCES artifacts(id) ON DELETE RESTRICT,
  source_artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  filename VARCHAR(240) NOT NULL,
  mime_type VARCHAR(160) NOT NULL,
  bucket VARCHAR(128) NOT NULL,
  storage_key TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  checksum_sha256 VARCHAR(64) NOT NULL,
  renderer_version VARCHAR(200) NOT NULL,
  output_json JSONB NOT NULL,
  PRIMARY KEY (export_job_id, ordinal),
  CONSTRAINT ck_export_output_size CHECK (size_bytes >= 0),
  CONSTRAINT ck_export_output_checksum CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_export_output_storage CHECK (
    storage_key NOT LIKE 'http%' AND storage_key NOT LIKE '%X-Amz-Signature%'
  )
);

-- statement-breakpoint

CREATE TABLE export_download_grants (
  grant_id UUID PRIMARY KEY,
  export_job_id UUID NOT NULL REFERENCES export_specs(export_job_id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  package_id UUID NOT NULL,
  actor_id VARCHAR(200) NOT NULL,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT ck_export_grant_expiry CHECK (expires_at > issued_at)
);

-- statement-breakpoint

CREATE INDEX ix_export_download_grants_job
ON export_download_grants (organization_id, export_job_id, issued_at);
