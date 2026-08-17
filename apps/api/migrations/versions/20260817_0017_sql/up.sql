CREATE TABLE video_generation_specs (
  video_job_id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  semantic_hash VARCHAR(64) NOT NULL,
  mode VARCHAR(32) NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  fps INTEGER NOT NULL,
  budget_limit_usd NUMERIC(20,8),
  spec_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_video_generation_operation UNIQUE (organization_id, operation_id),
  CONSTRAINT ck_video_generation_semantic_hash CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_video_generation_mode CHECK (
    mode IN ('TEXT_TO_VIDEO', 'IMAGE_TO_VIDEO', 'KEYFRAME_TO_VIDEO', 'PRODUCT_MOTION', 'LOOP')
  ),
  CONSTRAINT ck_video_generation_dimensions CHECK (
    width > 0 AND height > 0 AND width <= 8192 AND height <= 8192 AND fps > 0 AND fps <= 120
  ),
  CONSTRAINT ck_video_generation_budget CHECK (budget_limit_usd IS NULL OR budget_limit_usd >= 0)
);

-- statement-breakpoint

CREATE INDEX ix_video_generation_specs_project
ON video_generation_specs (organization_id, project_id, created_at);

-- statement-breakpoint

CREATE TABLE video_generation_jobs (
  video_job_id UUID PRIMARY KEY REFERENCES video_generation_specs(video_job_id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  status VARCHAR(32) NOT NULL,
  final_artifact_version_id UUID REFERENCES artifact_versions(id) ON DELETE SET NULL,
  final_durable_ref TEXT,
  provenance_json JSONB,
  job_json JSONB NOT NULL,
  error_code VARCHAR(240),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_video_generation_jobs_status CHECK (
    status IN (
      'PLANNED', 'WAITING_EXTERNAL', 'VALIDATING', 'COMPOSING', 'COMPLETED',
      'CANCEL_REQUESTED', 'CANCELLED', 'FAILED'
    )
  )
);

-- statement-breakpoint

CREATE INDEX ix_video_generation_jobs_status
ON video_generation_jobs (organization_id, status, updated_at);

-- statement-breakpoint

CREATE TABLE video_generation_shots (
  video_job_id UUID NOT NULL REFERENCES video_generation_specs(video_job_id) ON DELETE CASCADE,
  shot_id VARCHAR(160) NOT NULL,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  retry_ordinal INTEGER NOT NULL DEFAULT 0,
  paid_operation_id UUID NOT NULL,
  status VARCHAR(32) NOT NULL,
  shot_json JSONB NOT NULL,
  validation_json JSONB,
  artifact_version_id UUID REFERENCES artifact_versions(id) ON DELETE SET NULL,
  error_code VARCHAR(240),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (video_job_id, shot_id),
  CONSTRAINT uq_video_generation_shot_operation UNIQUE (organization_id, paid_operation_id),
  CONSTRAINT ck_video_generation_shot_ordinal CHECK (ordinal >= 0 AND retry_ordinal >= 0),
  CONSTRAINT ck_video_generation_shot_status CHECK (
    status IN ('PLANNED', 'WAITING_EXTERNAL', 'READY', 'FAILED', 'CANCELLED')
  )
);

-- statement-breakpoint

CREATE INDEX ix_video_generation_shots_status
ON video_generation_shots (organization_id, status, updated_at);

-- statement-breakpoint

CREATE TABLE video_provider_jobs (
  video_job_id UUID NOT NULL,
  shot_id VARCHAR(160) NOT NULL,
  retry_ordinal INTEGER NOT NULL,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  provider VARCHAR(120) NOT NULL,
  model VARCHAR(200) NOT NULL,
  capability VARCHAR(80) NOT NULL,
  provider_request_id VARCHAR(300) NOT NULL,
  queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_polled_at TIMESTAMPTZ,
  poll_attempts INTEGER NOT NULL DEFAULT 0,
  terminal_status VARCHAR(32),
  result_json JSONB NOT NULL,
  PRIMARY KEY (video_job_id, shot_id, retry_ordinal),
  FOREIGN KEY (video_job_id, shot_id)
    REFERENCES video_generation_shots(video_job_id, shot_id) ON DELETE CASCADE,
  CONSTRAINT ck_video_provider_poll_attempts CHECK (poll_attempts >= 0),
  CONSTRAINT ck_video_provider_request_id CHECK (length(provider_request_id) > 0),
  CONSTRAINT ck_video_provider_terminal_status CHECK (
    terminal_status IS NULL OR terminal_status IN ('COMPLETED', 'FAILED', 'CANCELLED')
  )
);

-- statement-breakpoint

CREATE INDEX ix_video_provider_jobs_pending
ON video_provider_jobs (organization_id, queued_at)
WHERE terminal_status IS NULL;

-- statement-breakpoint

CREATE TABLE video_generation_clips (
  video_job_id UUID NOT NULL,
  shot_id VARCHAR(160) NOT NULL,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  retry_ordinal INTEGER NOT NULL,
  artifact_version_id UUID REFERENCES artifact_versions(id) ON DELETE SET NULL,
  durable_ref TEXT NOT NULL,
  bucket VARCHAR(128) NOT NULL,
  storage_key TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  checksum_sha256 VARCHAR(64) NOT NULL,
  mime_type VARCHAR(80) NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  duration_seconds NUMERIC(12,3) NOT NULL,
  decodable_frames INTEGER NOT NULL,
  black_frame_ratio NUMERIC(8,6) NOT NULL DEFAULT 0,
  clip_json JSONB NOT NULL,
  PRIMARY KEY (video_job_id, shot_id, retry_ordinal),
  FOREIGN KEY (video_job_id, shot_id)
    REFERENCES video_generation_shots(video_job_id, shot_id) ON DELETE CASCADE,
  CONSTRAINT ck_video_clip_checksum CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_video_clip_probe CHECK (
    width > 0 AND height > 0 AND duration_seconds > 0 AND decodable_frames > 0
    AND black_frame_ratio >= 0 AND black_frame_ratio <= 1 AND size_bytes > 0
  ),
  CONSTRAINT ck_video_clip_storage_key CHECK (
    storage_key NOT LIKE 'http%' AND storage_key NOT LIKE '%X-Amz-Signature%'
  )
);

-- statement-breakpoint

CREATE TABLE video_generation_cost_projection (
  video_job_id UUID NOT NULL,
  shot_id VARCHAR(160) NOT NULL,
  retry_ordinal INTEGER NOT NULL,
  operation_id UUID NOT NULL,
  provider VARCHAR(120) NOT NULL,
  model VARCHAR(200) NOT NULL,
  provider_request_id VARCHAR(300),
  amount_usd NUMERIC(20,8),
  pricing_snapshot_id VARCHAR(160),
  monetary_owner VARCHAR(80) NOT NULL DEFAULT 'NODE27_MODEL_GATEWAY_SETTLEMENT',
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (video_job_id, shot_id, retry_ordinal),
  CONSTRAINT ck_video_cost_amount CHECK (amount_usd IS NULL OR amount_usd >= 0),
  CONSTRAINT ck_video_cost_owner CHECK (monetary_owner = 'NODE27_MODEL_GATEWAY_SETTLEMENT')
);

-- statement-breakpoint

CREATE INDEX ix_video_cost_operation
ON video_generation_cost_projection (operation_id);

-- statement-breakpoint

CREATE TABLE video_webhook_dedupe (
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  provider VARCHAR(120) NOT NULL,
  event_id VARCHAR(300) NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, provider, event_id)
);
