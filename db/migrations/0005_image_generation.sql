BEGIN;

CREATE TABLE IF NOT EXISTS image_generation_jobs (
  generation_id text PRIMARY KEY CHECK (generation_id ~ '^image-generation:[0-9a-f]{64}$'),
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  task_id uuid NOT NULL,
  operation_id uuid NOT NULL,
  semantic_hash text NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
  prompt_hash text NOT NULL CHECK (prompt_hash ~ '^[0-9a-f]{64}$'),
  prompt_compilation_ref text NOT NULL CHECK (btrim(prompt_compilation_ref) <> ''),
  mode text NOT NULL CHECK (mode IN (
    'TEXT_TO_IMAGE','REFERENCE_TO_IMAGE','PRODUCT_SCENE','STYLE_REFERENCE',
    'TRANSPARENT_ASSET','BACKGROUND_GENERATION','COMPOSITION_EXPLORATION'
  )),
  status text NOT NULL CHECK (status IN (
    'PENDING','RUNNING','PROVIDER_PENDING','VALIDATING','COMPLETED','PARTIAL','FAILED'
  )),
  spec_snapshot jsonb NOT NULL CHECK (jsonb_typeof(spec_snapshot) = 'object'),
  requested_variant_count integer NOT NULL CHECK (requested_variant_count BETWEEN 1 AND 16),
  selected_variant_count integer NOT NULL CHECK (
    selected_variant_count BETWEEN 1 AND requested_variant_count
  ),
  estimated_cost_per_variant_usd numeric(20,8) NOT NULL CHECK (estimated_cost_per_variant_usd >= 0),
  estimated_total_usd numeric(20,8) NOT NULL CHECK (estimated_total_usd >= 0),
  variant_decision_reasons jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
    jsonb_typeof(variant_decision_reasons) = 'array'
  ),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  error_code text NULL,
  UNIQUE (organization_id, operation_id),
  UNIQUE (organization_id, generation_id)
);

CREATE TABLE IF NOT EXISTS image_generation_candidates (
  candidate_id text PRIMARY KEY CHECK (candidate_id ~ '^image-candidate:[0-9a-f]{64}$'),
  organization_id uuid NOT NULL,
  generation_id text NOT NULL,
  variant_index integer NOT NULL CHECK (variant_index >= 1),
  variant_operation_id uuid NOT NULL,
  status text NOT NULL CHECK (
    status IN ('PROVIDER_PENDING','VALIDATING','READY','REJECTED','FAILED')
  ),
  provider text NULL,
  model text NULL,
  provider_request_id text NULL,
  provider_output_ref text NULL,
  storage_key text NULL CHECK (storage_key IS NULL OR position('://' in storage_key) = 0),
  mime_type text NULL,
  width integer NULL CHECK (width IS NULL OR width > 0),
  height integer NULL CHECK (height IS NULL OR height > 0),
  size_bytes bigint NULL CHECK (size_bytes IS NULL OR size_bytes >= 0),
  checksum_sha256 text NULL CHECK (
    checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'
  ),
  artifact_id uuid NULL,
  artifact_version_id uuid NULL,
  validation_snapshot jsonb NULL CHECK (
    validation_snapshot IS NULL OR jsonb_typeof(validation_snapshot) = 'object'
  ),
  provenance_snapshot_id text NULL CHECK (
    provenance_snapshot_id IS NULL
    OR provenance_snapshot_id ~ '^image-generation-provenance:[0-9a-f]{64}$'
  ),
  error_code text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, generation_id, variant_index),
  UNIQUE (organization_id, variant_operation_id),
  FOREIGN KEY (organization_id, generation_id)
    REFERENCES image_generation_jobs(organization_id, generation_id)
    ON DELETE CASCADE,
  FOREIGN KEY (organization_id, artifact_version_id)
    REFERENCES artifact_versions(organization_id, id)
);

COMMENT ON COLUMN image_generation_candidates.provider_output_ref IS
  'Transient/restricted provider reference only; never durable source of truth. storage_key is durable.';

CREATE TABLE IF NOT EXISTS image_generation_pending_invocations (
  candidate_id text PRIMARY KEY,
  organization_id uuid NOT NULL,
  generation_id text NOT NULL,
  variant_operation_id uuid NOT NULL,
  provider text NOT NULL CHECK (btrim(provider) <> ''),
  model text NOT NULL CHECK (btrim(model) <> ''),
  provider_request_id text NOT NULL CHECK (btrim(provider_request_id) <> ''),
  request_snapshot jsonb NOT NULL CHECK (jsonb_typeof(request_snapshot) = 'object'),
  result_snapshot jsonb NOT NULL CHECK (jsonb_typeof(result_snapshot) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, provider, model, provider_request_id),
  FOREIGN KEY (candidate_id)
    REFERENCES image_generation_candidates(candidate_id)
    ON DELETE CASCADE,
  FOREIGN KEY (organization_id, generation_id)
    REFERENCES image_generation_jobs(organization_id, generation_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS image_generation_provenance (
  snapshot_id text PRIMARY KEY CHECK (
    snapshot_id ~ '^image-generation-provenance:[0-9a-f]{64}$'
  ),
  organization_id uuid NOT NULL,
  generation_id text NOT NULL,
  candidate_id text NOT NULL,
  project_id uuid NOT NULL,
  task_id uuid NOT NULL,
  operation_id uuid NOT NULL,
  variant_operation_id uuid NOT NULL,
  variant_index integer NOT NULL CHECK (variant_index >= 1),
  provider text NOT NULL,
  model text NOT NULL,
  model_revision text NULL,
  provider_request_id text NULL,
  prompt_hash text NOT NULL CHECK (prompt_hash ~ '^[0-9a-f]{64}$'),
  prompt_template_version text NOT NULL,
  prompt_compilation_ref text NOT NULL,
  reference_asset_refs jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
    jsonb_typeof(reference_asset_refs) = 'array'
  ),
  seed bigint NULL CHECK (seed IS NULL OR seed >= 0),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  quality_profile text NOT NULL CHECK (quality_profile IN ('DRAFT','BALANCED','HIGH','MAX')),
  routing_reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
    jsonb_typeof(routing_reason_codes) = 'array'
  ),
  pricing_snapshot_id text NULL,
  cost_usd numeric(20,8) NULL CHECK (cost_usd IS NULL OR cost_usd >= 0),
  cost_confidence text NOT NULL,
  agent_run_id text NULL,
  recipe_version text NULL,
  skill_versions jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(skill_versions) = 'object'),
  code_git_sha text NOT NULL CHECK (code_git_sha ~ '^[0-9a-f]{40}$'),
  constraint_snapshot_hash text NOT NULL CHECK (constraint_snapshot_hash ~ '^[0-9a-f]{64}$'),
  brand_rule_set_version text NULL,
  identity_validation_snapshot_id text NULL,
  safety_metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(safety_metadata) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, generation_id, candidate_id),
  UNIQUE (organization_id, variant_operation_id),
  FOREIGN KEY (organization_id, generation_id)
    REFERENCES image_generation_jobs(organization_id, generation_id)
    ON DELETE CASCADE,
  FOREIGN KEY (candidate_id)
    REFERENCES image_generation_candidates(candidate_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS image_generation_cost_reconciliation (
  row_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  generation_id text NOT NULL,
  candidate_id text NOT NULL,
  operation_id uuid NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  provider_request_id text NULL,
  amount_usd numeric(20,8) NULL CHECK (amount_usd IS NULL OR amount_usd >= 0),
  confidence text NOT NULL,
  pricing_snapshot_id text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, generation_id, candidate_id),
  UNIQUE NULLS NOT DISTINCT (
    organization_id, operation_id, provider, model, provider_request_id
  ),
  FOREIGN KEY (organization_id, generation_id)
    REFERENCES image_generation_jobs(organization_id, generation_id)
    ON DELETE CASCADE,
  FOREIGN KEY (candidate_id)
    REFERENCES image_generation_candidates(candidate_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS image_generation_jobs_scope_idx
  ON image_generation_jobs (organization_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS image_generation_candidates_job_idx
  ON image_generation_candidates (organization_id, generation_id, status, variant_index);
CREATE INDEX IF NOT EXISTS image_generation_pending_idx
  ON image_generation_pending_invocations (organization_id, generation_id, updated_at);
CREATE INDEX IF NOT EXISTS image_generation_provenance_provider_idx
  ON image_generation_provenance (organization_id, provider, model, created_at DESC);
CREATE INDEX IF NOT EXISTS image_generation_cost_operation_idx
  ON image_generation_cost_reconciliation (organization_id, operation_id, created_at DESC);

COMMIT;
