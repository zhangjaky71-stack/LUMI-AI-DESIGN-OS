CREATE TABLE image_edit_specs (
  edit_id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  semantic_hash VARCHAR(64) NOT NULL,
  source_artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  source_asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
  source_asset_version VARCHAR(160) NOT NULL,
  source_checksum_sha256 VARCHAR(64) NOT NULL,
  spec_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_image_edit_specs_semantic_hash_format
    CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_image_edit_specs_source_checksum_format
    CHECK (source_checksum_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT uq_image_edit_spec_operation UNIQUE (organization_id, operation_id)
);

-- statement-breakpoint

CREATE INDEX ix_image_edit_specs_project
ON image_edit_specs (organization_id, project_id, created_at);

-- statement-breakpoint

CREATE TABLE image_edit_jobs (
  edit_id UUID PRIMARY KEY REFERENCES image_edit_specs(edit_id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  route VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  result_artifact_version_id UUID REFERENCES artifact_versions(id) ON DELETE SET NULL,
  result_design_document_version_id VARCHAR(200),
  result_asset_id UUID REFERENCES assets(id) ON DELETE SET NULL,
  provider VARCHAR(120),
  model VARCHAR(200),
  provider_request_id VARCHAR(300),
  provenance_snapshot_id VARCHAR(200),
  validation_decision VARCHAR(16),
  error_code VARCHAR(240),
  job_json JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_image_edit_jobs_route CHECK (
    route IN (
      'STRUCTURAL_IR_EDIT',
      'PIXEL_LOCAL_EDIT',
      'REGENERATE_REGION',
      'FULL_IMAGE_EDIT',
      'HYBRID'
    )
  ),
  CONSTRAINT ck_image_edit_jobs_status CHECK (
    status IN (
      'PLANNED',
      'QUEUED',
      'AWAITING_MASK_APPROVAL',
      'AWAITING_CONFIRMATION',
      'RUNNING',
      'PROVIDER_PENDING',
      'VALIDATING',
      'COMPLETED',
      'REPAIR_REQUIRED',
      'REJECTED',
      'FAILED',
      'CANCELLED'
    )
  ),
  CONSTRAINT ck_image_edit_jobs_validation_decision CHECK (
    validation_decision IS NULL OR validation_decision IN ('PASS', 'REPAIR', 'REJECT')
  )
);

-- statement-breakpoint

CREATE INDEX ix_image_edit_jobs_status
ON image_edit_jobs (organization_id, status, updated_at);

-- statement-breakpoint

CREATE TABLE image_edit_masks (
  edit_id UUID PRIMARY KEY REFERENCES image_edit_specs(edit_id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  mask_id UUID NOT NULL,
  version VARCHAR(160) NOT NULL,
  source VARCHAR(32) NOT NULL,
  checksum_sha256 VARCHAR(64) NOT NULL,
  source_checksum_sha256 VARCHAR(64) NOT NULL,
  source_width INTEGER NOT NULL,
  source_height INTEGER NOT NULL,
  editable_rect_json JSONB NOT NULL,
  durable_ref TEXT NOT NULL,
  preview_required BOOLEAN NOT NULL DEFAULT false,
  preview_approved_by VARCHAR(200),
  CONSTRAINT ck_image_edit_masks_source CHECK (
    source IN ('USER_BRUSH', 'DESIGN_IR', 'DETECTOR', 'AGENT_PROPOSED')
  ),
  CONSTRAINT ck_image_edit_masks_checksum_format CHECK (
    checksum_sha256 ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT ck_image_edit_masks_source_checksum_format CHECK (
    source_checksum_sha256 ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT ck_image_edit_masks_source_dimensions CHECK (
    source_width > 0 AND source_height > 0
  )
);

-- statement-breakpoint

CREATE INDEX ix_image_edit_masks_org
ON image_edit_masks (organization_id);

-- statement-breakpoint

CREATE TABLE image_edit_pending (
  edit_id UUID PRIMARY KEY REFERENCES image_edit_specs(edit_id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  provider VARCHAR(120) NOT NULL,
  model VARCHAR(200) NOT NULL,
  provider_request_id VARCHAR(300) NOT NULL,
  request_json JSONB NOT NULL,
  result_json JSONB NOT NULL,
  queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_polled_at TIMESTAMPTZ,
  poll_attempts INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT ck_image_edit_pending_poll_attempts CHECK (poll_attempts >= 0),
  CONSTRAINT ck_image_edit_pending_provider_request CHECK (length(provider_request_id) > 0)
);

-- statement-breakpoint

CREATE INDEX ix_image_edit_pending_provider
ON image_edit_pending (organization_id, provider, queued_at);

-- statement-breakpoint

CREATE TABLE image_edit_audits (
  edit_id UUID PRIMARY KEY REFERENCES image_edit_specs(edit_id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  snapshot_id VARCHAR(200) NOT NULL UNIQUE,
  provenance_json JSONB NOT NULL,
  validation_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- statement-breakpoint

CREATE TABLE image_edit_cost_projection (
  edit_id UUID PRIMARY KEY REFERENCES image_edit_specs(edit_id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  provider VARCHAR(120) NOT NULL,
  model VARCHAR(200) NOT NULL,
  provider_request_id VARCHAR(300),
  amount NUMERIC(20,8),
  confidence VARCHAR(32) NOT NULL,
  pricing_snapshot_id VARCHAR(160),
  monetary_owner VARCHAR(80) NOT NULL DEFAULT 'NODE27_MODEL_GATEWAY_SETTLEMENT',
  reconciled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_image_edit_cost_amount_nonnegative CHECK (amount IS NULL OR amount >= 0),
  CONSTRAINT ck_image_edit_cost_monetary_owner CHECK (
    monetary_owner = 'NODE27_MODEL_GATEWAY_SETTLEMENT'
  )
);

-- statement-breakpoint

CREATE INDEX ix_image_edit_cost_operation
ON image_edit_cost_projection (operation_id);
