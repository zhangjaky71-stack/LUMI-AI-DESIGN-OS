BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS asset_intelligence_index_versions (
  row_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  index_id text NOT NULL CHECK (btrim(index_id) <> ''),
  version text NOT NULL CHECK (btrim(version) <> ''),
  state text NOT NULL CHECK (state IN ('BUILDING','READY','ACTIVE','RETIRED','FAILED')),
  analyzer_version text NOT NULL CHECK (btrim(analyzer_version) <> ''),
  embedding_model_id text NOT NULL CHECK (btrim(embedding_model_id) <> ''),
  embedding_model_version text NOT NULL CHECK (btrim(embedding_model_version) <> ''),
  embedding_dimensions integer NOT NULL CHECK (embedding_dimensions > 0),
  embedding_space_id text NOT NULL CHECK (btrim(embedding_space_id) <> ''),
  registry_snapshot_id text NOT NULL CHECK (btrim(registry_snapshot_id) <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz NULL,
  retired_at timestamptz NULL,
  UNIQUE (organization_id, index_id),
  UNIQUE (organization_id, version, embedding_space_id),
  CHECK ((state = 'ACTIVE' AND activated_at IS NOT NULL) OR state <> 'ACTIVE')
);

CREATE UNIQUE INDEX IF NOT EXISTS asset_intelligence_one_active_index_per_org
  ON asset_intelligence_index_versions (organization_id)
  WHERE state = 'ACTIVE';

CREATE TABLE IF NOT EXISTS asset_intelligence_analysis_jobs (
  job_id text PRIMARY KEY CHECK (job_id ~ '^asset-analysis-job:[0-9a-f]{64}$'),
  organization_id uuid NOT NULL,
  asset_id uuid NOT NULL,
  asset_version text NOT NULL CHECK (btrim(asset_version) <> ''),
  index_id text NOT NULL,
  source_event_id text NOT NULL CHECK (btrim(source_event_id) <> ''),
  state text NOT NULL CHECK (state IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  error_code text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz NULL,
  finished_at timestamptz NULL,
  UNIQUE (organization_id, asset_id, asset_version, index_id),
  FOREIGN KEY (organization_id, index_id)
    REFERENCES asset_intelligence_index_versions(organization_id, index_id)
);

CREATE TABLE IF NOT EXISTS asset_intelligence_analysis_records (
  analysis_id text PRIMARY KEY CHECK (analysis_id ~ '^asset-analysis:[0-9a-f]{64}$'),
  organization_id uuid NOT NULL,
  asset_id uuid NOT NULL,
  asset_version text NOT NULL CHECK (btrim(asset_version) <> ''),
  project_id uuid NULL,
  brand_id uuid NULL,
  index_id text NOT NULL,
  index_version text NOT NULL CHECK (btrim(index_version) <> ''),
  state text NOT NULL CHECK (
    state IN ('PENDING','ANALYZING','READY','FAILED','STALE','DELETING','DELETED')
  ),
  checksum_sha256 text NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  mime_type text NOT NULL CHECK (btrim(mime_type) <> ''),
  media_type text NOT NULL CHECK (btrim(media_type) <> ''),
  rights text NOT NULL CHECK (rights IN ('USER_OWNED','LICENSED','UNKNOWN')),
  commercial_use_allowed boolean NOT NULL DEFAULT false,
  training_authorized boolean NOT NULL DEFAULT false,
  permission_tags jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
    jsonb_typeof(permission_tags) = 'array'
  ),
  preview_ref text NULL,
  semantic_description text NULL,
  visual_tags jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(visual_tags) = 'array'),
  perceptual_hash text NULL,
  language text NULL,
  analyzer_bundle jsonb NOT NULL CHECK (jsonb_typeof(analyzer_bundle) = 'object'),
  error_code text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz NULL,
  UNIQUE (organization_id, asset_id, asset_version, index_id),
  UNIQUE (organization_id, analysis_id),
  FOREIGN KEY (organization_id, index_id)
    REFERENCES asset_intelligence_index_versions(organization_id, index_id)
);

CREATE TABLE IF NOT EXISTS asset_intelligence_metadata_fields (
  row_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  analysis_id text NOT NULL,
  field_key text NOT NULL CHECK (btrim(field_key) <> ''),
  field_value jsonb NOT NULL,
  source text NOT NULL CHECK (source IN ('AUTO','USER','SYSTEM')),
  confidence double precision NULL CHECK (
    confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
  ),
  analyzer_id text NULL,
  analyzer_version text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, analysis_id, field_key),
  FOREIGN KEY (organization_id, analysis_id)
    REFERENCES asset_intelligence_analysis_records(organization_id, analysis_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_intelligence_ocr_blocks (
  row_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  analysis_id text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  text_value text NOT NULL,
  language text NULL,
  confidence double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  bbox jsonb NOT NULL CHECK (jsonb_typeof(bbox) = 'object'),
  analyzer_id text NULL,
  analyzer_version text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, analysis_id, ordinal),
  FOREIGN KEY (organization_id, analysis_id)
    REFERENCES asset_intelligence_analysis_records(organization_id, analysis_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_intelligence_regions (
  row_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  analysis_id text NOT NULL,
  region_id text NOT NULL CHECK (btrim(region_id) <> ''),
  label text NOT NULL CHECK (btrim(label) <> ''),
  confidence double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  bbox jsonb NOT NULL CHECK (jsonb_typeof(bbox) = 'object'),
  analyzer_id text NULL,
  analyzer_version text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, analysis_id, region_id),
  FOREIGN KEY (organization_id, analysis_id)
    REFERENCES asset_intelligence_analysis_records(organization_id, analysis_id)
    ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS asset_intelligence_embeddings (
  row_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  analysis_id text NOT NULL,
  asset_id uuid NOT NULL,
  asset_version text NOT NULL,
  index_id text NOT NULL,
  embedding_space_id text NOT NULL,
  embedding_model_id text NOT NULL,
  embedding_model_version text NOT NULL,
  preprocessor_version text NOT NULL,
  embedding_dimensions integer NOT NULL CHECK (embedding_dimensions > 0),
  embedding vector NOT NULL,
  content_hash text NOT NULL CHECK (btrim(content_hash) <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, asset_id, asset_version, index_id),
  FOREIGN KEY (organization_id, analysis_id)
    REFERENCES asset_intelligence_analysis_records(organization_id, analysis_id)
    ON DELETE CASCADE,
  FOREIGN KEY (organization_id, index_id)
    REFERENCES asset_intelligence_index_versions(organization_id, index_id),
  CHECK (vector_dims(embedding) = embedding_dimensions)
);

CREATE TABLE IF NOT EXISTS asset_intelligence_duplicate_edges (
  row_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  index_id text NOT NULL,
  source_asset_id uuid NOT NULL,
  candidate_asset_id uuid NOT NULL,
  tier text NOT NULL CHECK (
    tier IN ('EXACT','PERCEPTUAL_NEAR_DUPLICATE','SEMANTIC_SIMILAR')
  ),
  score double precision NOT NULL CHECK (score >= -1 AND score <= 1),
  policy_version text NOT NULL CHECK (btrim(policy_version) <> ''),
  detail text NOT NULL,
  auto_delete boolean NOT NULL DEFAULT false CHECK (auto_delete = false),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (source_asset_id <> candidate_asset_id),
  UNIQUE (organization_id, index_id, source_asset_id, candidate_asset_id, tier),
  FOREIGN KEY (organization_id, index_id)
    REFERENCES asset_intelligence_index_versions(organization_id, index_id)
);

CREATE TABLE IF NOT EXISTS asset_intelligence_usage_signals (
  row_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NULL,
  asset_id uuid NOT NULL,
  signal text NOT NULL CHECK (signal IN ('SELECTED','APPROVED','REJECTED')),
  actor_id uuid NULL,
  training_authorization_granted boolean NOT NULL DEFAULT false,
  occurred_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS asset_intelligence_delete_tombstones (
  row_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  asset_id uuid NOT NULL,
  asset_version text NULL,
  requested_at timestamptz NOT NULL,
  reconciled_at timestamptz NULL,
  UNIQUE (organization_id, asset_id, asset_version)
);

CREATE INDEX IF NOT EXISTS asset_intelligence_record_scope_idx
  ON asset_intelligence_analysis_records (
    organization_id, index_id, project_id, brand_id, rights, state, created_at DESC
  )
  WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS asset_intelligence_record_checksum_idx
  ON asset_intelligence_analysis_records (organization_id, index_id, checksum_sha256)
  WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS asset_intelligence_record_phash_idx
  ON asset_intelligence_analysis_records (organization_id, index_id, perceptual_hash)
  WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS asset_intelligence_ocr_text_idx
  ON asset_intelligence_ocr_blocks USING gin (to_tsvector('simple', text_value));
CREATE INDEX IF NOT EXISTS asset_intelligence_metadata_key_idx
  ON asset_intelligence_metadata_fields (organization_id, analysis_id, field_key, source);
CREATE INDEX IF NOT EXISTS asset_intelligence_usage_idx
  ON asset_intelligence_usage_signals (organization_id, asset_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS asset_intelligence_tombstone_pending_idx
  ON asset_intelligence_delete_tombstones (organization_id, requested_at)
  WHERE reconciled_at IS NULL;

-- Scope-first vector retrieval primitive. Application authorization remains mandatory, but
-- organization/project/permission/rights constraints are part of the SQL candidate query itself.
CREATE OR REPLACE FUNCTION asset_intelligence_semantic_candidates(
  p_organization_id uuid,
  p_index_id text,
  p_query_embedding vector,
  p_permission_tags text[],
  p_allowed_rights text[],
  p_project_ids uuid[] DEFAULT NULL,
  p_brand_ids uuid[] DEFAULT NULL,
  p_commercial_use boolean DEFAULT false,
  p_limit integer DEFAULT 20
)
RETURNS TABLE (
  asset_id uuid,
  asset_version text,
  semantic_score double precision
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    r.asset_id,
    r.asset_version,
    1 - (e.embedding <=> p_query_embedding) AS semantic_score
  FROM asset_intelligence_analysis_records r
  JOIN asset_intelligence_embeddings e
    ON e.organization_id = r.organization_id
   AND e.analysis_id = r.analysis_id
   AND e.index_id = r.index_id
  WHERE r.organization_id = p_organization_id
    AND r.index_id = p_index_id
    AND r.state = 'READY'
    AND r.deleted_at IS NULL
    AND r.rights = ANY(p_allowed_rights)
    AND (NOT p_commercial_use OR r.commercial_use_allowed = true)
    AND (p_project_ids IS NULL OR r.project_id = ANY(p_project_ids))
    AND (p_brand_ids IS NULL OR r.brand_id = ANY(p_brand_ids))
    AND to_jsonb(p_permission_tags) @> r.permission_tags
    AND vector_dims(e.embedding) = vector_dims(p_query_embedding)
  ORDER BY e.embedding <=> p_query_embedding, r.asset_id
  LIMIT GREATEST(1, LEAST(p_limit, 200));
$$;

COMMIT;
