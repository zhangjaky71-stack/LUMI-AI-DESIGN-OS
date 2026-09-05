BEGIN;

CREATE TABLE IF NOT EXISTS video_generation_jobs (
  id text NOT NULL,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  task_id uuid NOT NULL,
  operation_id uuid NOT NULL,
  semantic_hash char(64) NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
  storyboard_hash char(64) NOT NULL CHECK (storyboard_hash ~ '^[0-9a-f]{64}$'),
  mode text NOT NULL CHECK (mode IN ('TEXT_TO_VIDEO','IMAGE_TO_VIDEO','STORYBOARD_MULTI_SHOT')),
  status text NOT NULL CHECK (status IN ('SUBMITTING','WAITING_EXTERNAL','VALIDATING','COMPOSING','COMPLETED','PARTIAL','FAILED','CANCELLED')),
  duration_seconds numeric(12,3) NOT NULL CHECK (duration_seconds > 0),
  aspect_ratio text NOT NULL CHECK (aspect_ratio <> ''),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  fps integer NOT NULL CHECK (fps > 0),
  budget_limit_usd numeric(20,8) NOT NULL CHECK (budget_limit_usd >= 0),
  estimated_cost_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK (estimated_cost_usd >= 0),
  actual_cost_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK (actual_cost_usd >= 0),
  quality_retry_limit smallint NOT NULL DEFAULT 1 CHECK (quality_retry_limit BETWEEN 0 AND 2),
  allow_optional_shot_drop boolean NOT NULL DEFAULT false,
  brand_rule_set_version text NULL,
  final_artifact_version_id uuid NULL,
  spec_snapshot jsonb NOT NULL,
  error_code text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, id),
  UNIQUE (organization_id, operation_id),
  FOREIGN KEY (organization_id, final_artifact_version_id) REFERENCES artifact_versions(organization_id, id)
);

CREATE TABLE IF NOT EXISTS video_generation_shots (
  organization_id uuid NOT NULL,
  video_job_id text NOT NULL,
  shot_id text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 1),
  duration_seconds numeric(12,3) NOT NULL CHECK (duration_seconds > 0),
  optional boolean NOT NULL DEFAULT false,
  status text NOT NULL CHECK (status IN ('QUEUED','WAITING_EXTERNAL','READY','FAILED','DROPPED','CANCELLED')),
  current_paid_operation_id uuid NOT NULL,
  attempt_count smallint NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 2),
  excluded_provider_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  attempt_artifact_version_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  provider text NULL,
  model text NULL,
  provider_request_id text NULL,
  clip_artifact_version_id uuid NULL,
  error_code text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, video_job_id, shot_id),
  UNIQUE (organization_id, current_paid_operation_id),
  FOREIGN KEY (organization_id, video_job_id) REFERENCES video_generation_jobs(organization_id, id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, clip_artifact_version_id) REFERENCES artifact_versions(organization_id, id)
);

CREATE TABLE IF NOT EXISTS video_provider_jobs (
  organization_id uuid NOT NULL,
  video_job_id text NOT NULL,
  shot_id text NOT NULL,
  paid_operation_id uuid NOT NULL,
  request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
  provider text NOT NULL,
  model text NOT NULL,
  provider_request_id text NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING','SUCCEEDED','FAILED','CANCELLED')),
  result_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, paid_operation_id),
  UNIQUE (organization_id, provider, model, provider_request_id),
  FOREIGN KEY (organization_id, video_job_id, shot_id) REFERENCES video_generation_shots(organization_id, video_job_id, shot_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS video_provider_jobs_one_active_attempt_idx
  ON video_provider_jobs (organization_id, video_job_id, shot_id)
  WHERE active;

CREATE TABLE IF NOT EXISTS video_generation_cost_reconciliation (
  organization_id uuid NOT NULL,
  paid_operation_id uuid NOT NULL,
  video_job_id text NOT NULL,
  shot_id text NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  provider_request_id text NULL,
  amount_usd numeric(20,8) NULL CHECK (amount_usd IS NULL OR amount_usd >= 0),
  confidence text NOT NULL CHECK (confidence IN ('EXACT','ESTIMATED','UNKNOWN','exact','estimated','unknown')),
  pricing_snapshot_id text NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, paid_operation_id),
  FOREIGN KEY (organization_id, video_job_id, shot_id) REFERENCES video_generation_shots(organization_id, video_job_id, shot_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS video_timelines (
  organization_id uuid NOT NULL,
  video_job_id text NOT NULL,
  timeline_hash char(64) NOT NULL CHECK (timeline_hash ~ '^[0-9a-f]{64}$'),
  timeline_version integer NOT NULL DEFAULT 1 CHECK (timeline_version >= 1),
  timeline_spec jsonb NOT NULL,
  final_artifact_version_id uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, video_job_id, timeline_version),
  UNIQUE (organization_id, video_job_id, timeline_hash),
  FOREIGN KEY (organization_id, video_job_id) REFERENCES video_generation_jobs(organization_id, id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, final_artifact_version_id) REFERENCES artifact_versions(organization_id, id)
);

CREATE TABLE IF NOT EXISTS video_generation_provenance (
  snapshot_id text PRIMARY KEY,
  organization_id uuid NOT NULL,
  video_job_id text NOT NULL,
  shot_id text NULL,
  paid_operation_id uuid NULL,
  storyboard_hash char(64) NOT NULL CHECK (storyboard_hash ~ '^[0-9a-f]{64}$'),
  prompt_hash char(64) NULL CHECK (prompt_hash IS NULL OR prompt_hash ~ '^[0-9a-f]{64}$'),
  source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  continuity_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  provider text NULL,
  model text NULL,
  provider_request_id text NULL,
  routing_reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  pricing_snapshot_id text NULL,
  cost_usd numeric(20,8) NULL CHECK (cost_usd IS NULL OR cost_usd >= 0),
  cost_confidence text NULL,
  brand_rule_set_version text NULL,
  identity_validation_snapshot_id text NULL,
  timeline_hash char(64) NULL CHECK (timeline_hash IS NULL OR timeline_hash ~ '^[0-9a-f]{64}$'),
  code_git_sha char(40) NOT NULL CHECK (code_git_sha ~ '^[0-9a-f]{40}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, snapshot_id),
  FOREIGN KEY (organization_id, video_job_id) REFERENCES video_generation_jobs(organization_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS video_validation_findings (
  id bigserial PRIMARY KEY,
  organization_id uuid NOT NULL,
  video_job_id text NOT NULL,
  shot_id text NULL,
  paid_operation_id uuid NULL,
  scope text NOT NULL CHECK (scope IN ('SHOT','FINAL')),
  validator text NOT NULL,
  status text NOT NULL CHECK (status IN ('PASS','FAIL','UNAVAILABLE')),
  severity text NOT NULL CHECK (severity IN ('HARD','SOFT','ADVISORY')),
  reason_code text NOT NULL,
  evidence_ref text NULL,
  expected jsonb NULL,
  actual jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (organization_id, video_job_id) REFERENCES video_generation_jobs(organization_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS video_generation_jobs_status_idx
  ON video_generation_jobs (organization_id, status, updated_at);
CREATE INDEX IF NOT EXISTS video_generation_shots_status_idx
  ON video_generation_shots (organization_id, video_job_id, status, ordinal);
CREATE INDEX IF NOT EXISTS video_provider_jobs_request_idx
  ON video_provider_jobs (organization_id, provider, model, provider_request_id);
CREATE INDEX IF NOT EXISTS video_validation_findings_job_idx
  ON video_validation_findings (organization_id, video_job_id, shot_id);

-- Provider completion rows are retained. Production adapters transition active=false;
-- they do not delete terminal attempts. This makes post-provider worker crashes replayable.
-- Provider-native output URLs belong only in restricted/transient result snapshots and
-- must never replace Artifact storage_key/checksum as durable truth.

COMMIT;
