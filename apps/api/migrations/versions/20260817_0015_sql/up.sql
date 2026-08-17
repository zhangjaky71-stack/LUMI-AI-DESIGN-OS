CREATE TABLE image_generation_specs (
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  semantic_hash VARCHAR(64) NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
  spec_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, operation_id)
);

-- statement-breakpoint

CREATE INDEX ix_image_generation_specs_project
  ON image_generation_specs(organization_id, project_id);

-- statement-breakpoint

CREATE TABLE image_generation_jobs (
  generation_id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  semantic_hash VARCHAR(64) NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
  status VARCHAR(32) NOT NULL CHECK (
    status IN ('QUEUED','RUNNING','PROVIDER_PENDING','VALIDATING','COMPLETED','PARTIAL','FAILED','CANCELLED')
  ),
  requested_variants INTEGER NOT NULL CHECK (requested_variants BETWEEN 1 AND 16),
  selected_variants INTEGER NOT NULL CHECK (
    selected_variants BETWEEN 1 AND requested_variants
  ),
  estimated_cost_per_variant NUMERIC(20,8) NOT NULL CHECK (estimated_cost_per_variant >= 0),
  job_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  UNIQUE (organization_id, operation_id),
  UNIQUE (generation_id, organization_id)
);

-- statement-breakpoint

CREATE INDEX ix_image_generation_jobs_org_status
  ON image_generation_jobs(organization_id, status, updated_at);

-- statement-breakpoint

CREATE INDEX ix_image_generation_jobs_project_created
  ON image_generation_jobs(organization_id, project_id, created_at);

-- statement-breakpoint

CREATE TABLE image_generation_candidates (
  candidate_id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  generation_id UUID NOT NULL,
  variant_index INTEGER NOT NULL CHECK (variant_index BETWEEN 1 AND 16),
  variant_operation_id UUID NOT NULL,
  status VARCHAR(32) NOT NULL CHECK (
    status IN ('QUEUED','PROVIDER_PENDING','VALIDATING','READY','REJECTED','FAILED','CANCELLED')
  ),
  provider VARCHAR(120),
  model VARCHAR(200),
  model_revision VARCHAR(200),
  registry_snapshot_id VARCHAR(200),
  provider_request_id VARCHAR(300),
  bucket VARCHAR(128),
  storage_key TEXT,
  checksum_sha256 VARCHAR(64) CHECK (
    checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'
  ),
  mime_type VARCHAR(255),
  width INTEGER CHECK (width IS NULL OR width > 0),
  height INTEGER CHECK (height IS NULL OR height > 0),
  size_bytes BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
  artifact_id UUID REFERENCES artifacts(id) ON DELETE SET NULL,
  artifact_version_id UUID REFERENCES artifact_versions(id) ON DELETE SET NULL,
  validation_json JSONB,
  provenance_snapshot_id VARCHAR(160),
  cost_amount NUMERIC(20,8) CHECK (cost_amount IS NULL OR cost_amount >= 0),
  cost_confidence VARCHAR(32),
  pricing_snapshot_id VARCHAR(160),
  routing_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  error_code VARCHAR(200),
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT fk_image_generation_candidate_job_tenant
    FOREIGN KEY (generation_id, organization_id)
    REFERENCES image_generation_jobs(generation_id, organization_id)
    ON DELETE CASCADE,
  UNIQUE (generation_id, variant_index),
  UNIQUE (organization_id, variant_operation_id),
  UNIQUE (candidate_id, organization_id, generation_id)
);

-- statement-breakpoint

CREATE INDEX ix_image_generation_candidates_status
  ON image_generation_candidates(organization_id, status, updated_at);

-- statement-breakpoint

CREATE TABLE image_generation_pending (
  candidate_id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  generation_id UUID NOT NULL,
  provider VARCHAR(120) NOT NULL,
  model VARCHAR(200) NOT NULL,
  provider_request_id VARCHAR(300) NOT NULL,
  request_json JSONB NOT NULL,
  result_json JSONB NOT NULL,
  queued_at TIMESTAMPTZ NOT NULL,
  last_polled_at TIMESTAMPTZ,
  poll_attempts INTEGER NOT NULL DEFAULT 0 CHECK (poll_attempts >= 0),
  CONSTRAINT fk_image_generation_pending_candidate_tenant
    FOREIGN KEY (candidate_id, organization_id, generation_id)
    REFERENCES image_generation_candidates(candidate_id, organization_id, generation_id)
    ON DELETE CASCADE
);

-- statement-breakpoint

CREATE INDEX ix_image_generation_pending_provider
  ON image_generation_pending(organization_id, provider, queued_at);

-- statement-breakpoint

CREATE TABLE image_generation_cost_projection (
  candidate_id UUID PRIMARY KEY REFERENCES image_generation_candidates(candidate_id) ON DELETE CASCADE,
  generation_id UUID NOT NULL REFERENCES image_generation_jobs(generation_id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  provider VARCHAR(120) NOT NULL,
  model VARCHAR(200) NOT NULL,
  provider_request_id VARCHAR(300),
  amount NUMERIC(20,8) CHECK (amount IS NULL OR amount >= 0),
  confidence VARCHAR(32) NOT NULL,
  pricing_snapshot_id VARCHAR(160),
  monetary_owner VARCHAR(80) NOT NULL DEFAULT 'NODE27_MODEL_GATEWAY_SETTLEMENT'
    CHECK (monetary_owner = 'NODE27_MODEL_GATEWAY_SETTLEMENT'),
  reconciled_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- statement-breakpoint

CREATE INDEX ix_image_generation_cost_generation
  ON image_generation_cost_projection(generation_id);

-- statement-breakpoint

CREATE OR REPLACE FUNCTION enforce_image_generation_tenant_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  job_org UUID;
BEGIN
  SELECT organization_id INTO job_org
  FROM image_generation_jobs WHERE generation_id = NEW.generation_id;
  IF job_org IS NULL OR job_org <> NEW.organization_id THEN
    RAISE EXCEPTION 'image generation tenant mismatch';
  END IF;
  RETURN NEW;
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_image_generation_candidate_tenant
BEFORE INSERT OR UPDATE ON image_generation_candidates
FOR EACH ROW EXECUTE FUNCTION enforce_image_generation_tenant_scope();

-- statement-breakpoint

COMMENT ON TABLE image_generation_cost_projection IS
  'NODE-46 audit projection only; NODE-27 settlement through NODE-22 is monetary truth.';
