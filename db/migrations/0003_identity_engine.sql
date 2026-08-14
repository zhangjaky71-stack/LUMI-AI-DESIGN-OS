BEGIN;

CREATE TABLE IF NOT EXISTS identity_threshold_profiles (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  identity_type text NOT NULL CHECK (
    identity_type IN ('PRODUCT','LOGO','CHARACTER','FACE','STYLE_REFERENCE')
  ),
  scenario text NOT NULL CHECK (
    scenario IN ('STRICT_PRESERVE','BACKGROUND_REPLACEMENT','CREATIVE_REDRAW','STYLE_REFERENCE')
  ),
  version text NOT NULL CHECK (btrim(version) <> ''),
  status text NOT NULL CHECK (status IN ('DRAFT','PUBLISHED','RETIRED')),
  threshold double precision NOT NULL CHECK (threshold >= 0 AND threshold <= 100),
  review_floor double precision NOT NULL CHECK (review_floor >= 0 AND review_floor <= threshold),
  minimum_confidence double precision NOT NULL CHECK (
    minimum_confidence >= 0 AND minimum_confidence <= 1
  ),
  signal_weights jsonb NOT NULL CHECK (jsonb_typeof(signal_weights) = 'object'),
  required_signals jsonb NOT NULL CHECK (jsonb_typeof(required_signals) = 'array'),
  model_bundle_version text NOT NULL CHECK (btrim(model_bundle_version) <> ''),
  preprocessor_version text NOT NULL CHECK (btrim(preprocessor_version) <> ''),
  calibration_dataset_version text NOT NULL CHECK (btrim(calibration_dataset_version) <> ''),
  metrics jsonb NOT NULL CHECK (jsonb_typeof(metrics) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz NULL,
  UNIQUE (organization_id, id),
  UNIQUE (organization_id, id, version),
  CHECK (
    identity_type NOT IN ('PRODUCT','LOGO')
    OR jsonb_array_length(required_signals) >= 2
  ),
  CHECK (
    status <> 'PUBLISHED'
    OR (
      published_at IS NOT NULL
      AND COALESCE((metrics->>'positive_count')::integer, 0) > 0
      AND (
        COALESCE((metrics->>'negative_count')::integer, 0)
        + COALESCE((metrics->>'near_miss_count')::integer, 0)
      ) > 0
    )
  )
);

CREATE TABLE IF NOT EXISTS identity_calibration_samples (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  threshold_profile_id uuid NOT NULL,
  threshold_profile_version text NOT NULL,
  calibration_dataset_version text NOT NULL,
  identity_type text NOT NULL CHECK (
    identity_type IN ('PRODUCT','LOGO','CHARACTER','FACE','STYLE_REFERENCE')
  ),
  scenario text NOT NULL CHECK (
    scenario IN ('STRICT_PRESERVE','BACKGROUND_REPLACEMENT','CREATIVE_REDRAW','STYLE_REFERENCE')
  ),
  label text NOT NULL CHECK (label IN ('POSITIVE','NEGATIVE','NEAR_MISS')),
  score double precision NOT NULL CHECK (score >= 0 AND score <= 100),
  sample_asset_id uuid NULL,
  notes text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, threshold_profile_id, threshold_profile_version, id),
  FOREIGN KEY (organization_id, threshold_profile_id, threshold_profile_version)
    REFERENCES identity_threshold_profiles(organization_id, id, version)
);

CREATE TABLE IF NOT EXISTS identity_reference_sets (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NULL,
  brand_profile_id uuid NULL,
  identity_type text NOT NULL CHECK (
    identity_type IN ('PRODUCT','LOGO','CHARACTER','FACE','STYLE_REFERENCE')
  ),
  version text NOT NULL CHECK (btrim(version) <> ''),
  status text NOT NULL CHECK (status IN ('DRAFT','PUBLISHED','ARCHIVED')),
  threshold_profile_id uuid NOT NULL,
  threshold_profile_version text NOT NULL,
  canonical_asset_ids jsonb NOT NULL CHECK (
    jsonb_typeof(canonical_asset_ids) = 'array' AND jsonb_array_length(canonical_asset_ids) > 0
  ),
  notes text NULL,
  face_explicit_processing_consent boolean NOT NULL DEFAULT false,
  face_processing_purpose text NULL,
  face_retention_until timestamptz NULL,
  persistent_biometric_index boolean NOT NULL DEFAULT false CHECK (persistent_biometric_index = false),
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz NULL,
  UNIQUE (organization_id, id),
  UNIQUE (organization_id, id, version),
  FOREIGN KEY (organization_id, threshold_profile_id, threshold_profile_version)
    REFERENCES identity_threshold_profiles(organization_id, id, version),
  CHECK (
    identity_type <> 'FACE'
    OR (
      persistent_biometric_index = false
      AND face_explicit_processing_consent = true
      AND btrim(COALESCE(face_processing_purpose, '')) <> ''
      AND face_retention_until IS NOT NULL
    )
  ),
  CHECK ((status = 'PUBLISHED' AND published_at IS NOT NULL) OR status <> 'PUBLISHED')
);

CREATE TABLE IF NOT EXISTS identity_reference_views (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  reference_set_id uuid NOT NULL,
  reference_set_version text NOT NULL,
  asset_id uuid NOT NULL,
  asset_version text NOT NULL CHECK (btrim(asset_version) <> ''),
  role text NULL,
  region jsonb NULL,
  checksum_sha256 text NULL CHECK (
    checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'
  ),
  notes text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, reference_set_id, reference_set_version, id),
  FOREIGN KEY (organization_id, reference_set_id, reference_set_version)
    REFERENCES identity_reference_sets(organization_id, id, version)
);

CREATE TABLE IF NOT EXISTS identity_validation_reports (
  id text PRIMARY KEY,
  organization_id uuid NOT NULL,
  identity_id uuid NOT NULL,
  reference_set_version text NOT NULL,
  artifact_version_id uuid NULL,
  severity text NOT NULL CHECK (severity IN ('HARD','SOFT','ADVISORY')),
  scenario text NOT NULL CHECK (
    scenario IN ('STRICT_PRESERVE','BACKGROUND_REPLACEMENT','CREATIVE_REDRAW','STYLE_REFERENCE')
  ),
  status text NOT NULL CHECK (status IN ('PASS','FAIL','REVIEW','UNAVAILABLE')),
  identity_score double precision NULL CHECK (
    identity_score IS NULL OR (identity_score >= 0 AND identity_score <= 100)
  ),
  confidence double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  threshold double precision NOT NULL CHECK (threshold >= 0 AND threshold <= 100),
  review_floor double precision NOT NULL CHECK (review_floor >= 0 AND review_floor <= threshold),
  threshold_profile_id uuid NOT NULL,
  threshold_profile_version text NOT NULL,
  calibration_dataset_version text NOT NULL,
  provider_id text NOT NULL,
  provider_version text NOT NULL,
  preprocessor_version text NOT NULL,
  signal_scores jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  candidate_region jsonb NULL,
  reason_code text NULL,
  identity_validation_snapshot_id text NOT NULL CHECK (
    identity_validation_snapshot_id ~ '^identity-validation:[0-9a-f]{64}$'
  ),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, identity_id, reference_set_version)
    REFERENCES identity_reference_sets(organization_id, id, version),
  FOREIGN KEY (organization_id, threshold_profile_id, threshold_profile_version)
    REFERENCES identity_threshold_profiles(organization_id, id, version),
  CHECK (NOT (status = 'PASS' AND identity_score IS NULL))
);

CREATE TABLE IF NOT EXISTS identity_validation_batches (
  id text PRIMARY KEY CHECK (id ~ '^identity-batch:[0-9a-f]{64}$'),
  organization_id uuid NOT NULL,
  artifact_version_id uuid NOT NULL,
  report_ids jsonb NOT NULL CHECK (
    jsonb_typeof(report_ids) = 'array' AND jsonb_array_length(report_ids) > 0
  ),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, id)
);

ALTER TABLE artifact_versions
  ADD COLUMN IF NOT EXISTS identity_validation_snapshot_id text NULL;

ALTER TABLE artifact_provenance
  ADD COLUMN IF NOT EXISTS identity_validation_snapshot_id text NULL;

CREATE INDEX IF NOT EXISTS identity_profiles_lookup_idx
  ON identity_threshold_profiles (organization_id, identity_type, scenario, status, created_at DESC);
CREATE INDEX IF NOT EXISTS identity_calibration_profile_idx
  ON identity_calibration_samples (
    organization_id, threshold_profile_id, threshold_profile_version, calibration_dataset_version
  );
CREATE INDEX IF NOT EXISTS identity_reference_scope_idx
  ON identity_reference_sets (organization_id, project_id, brand_profile_id, identity_type, status);
CREATE INDEX IF NOT EXISTS identity_reference_views_asset_idx
  ON identity_reference_views (organization_id, asset_id, asset_version);
CREATE INDEX IF NOT EXISTS identity_reports_identity_idx
  ON identity_validation_reports (organization_id, identity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS identity_reports_artifact_idx
  ON identity_validation_reports (organization_id, artifact_version_id, created_at DESC);

COMMIT;
