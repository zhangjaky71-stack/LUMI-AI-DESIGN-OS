BEGIN;

CREATE TABLE IF NOT EXISTS quality_profiles (
  profile_id text NOT NULL,
  version text NOT NULL,
  name text NOT NULL CHECK (name IN ('exploration','production-web','brand-strict','product-strict','print','social-fast')),
  definition jsonb NOT NULL,
  status text NOT NULL DEFAULT 'PUBLISHED' CHECK (status IN ('DRAFT','PUBLISHED','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, version)
);

CREATE TABLE IF NOT EXISTS quality_grader_calibrations (
  grader_id text NOT NULL,
  grader_version text NOT NULL,
  dataset_version text NOT NULL,
  model_provider text NOT NULL,
  model_name text NOT NULL,
  model_version text NOT NULL,
  prompt_version text NOT NULL,
  sample_count integer NOT NULL CHECK (sample_count >= 20),
  precision double precision NOT NULL CHECK (precision BETWEEN 0 AND 1),
  recall double precision NOT NULL CHECK (recall BETWEEN 0 AND 1),
  f1 double precision NOT NULL CHECK (f1 BETWEEN 0 AND 1),
  false_positive_rate double precision NOT NULL CHECK (false_positive_rate BETWEEN 0 AND 1),
  false_negative_rate double precision NOT NULL CHECK (false_negative_rate BETWEEN 0 AND 1),
  inter_rater_agreement double precision NOT NULL CHECK (inter_rater_agreement BETWEEN 0 AND 1),
  approved boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz NULL,
  PRIMARY KEY (grader_id, grader_version, dataset_version),
  CHECK (NOT approved OR (f1 >= 0.60 AND inter_rater_agreement >= 0.50))
);

CREATE TABLE IF NOT EXISTS quality_results (
  quality_result_id text PRIMARY KEY CHECK (quality_result_id LIKE 'quality-result:%'),
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  artifact_id uuid NOT NULL,
  artifact_version_id uuid NOT NULL,
  design_document_version_id text NOT NULL,
  profile_id text NOT NULL,
  profile_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('PASS','PASS_WITH_WARNINGS','FAIL_REPAIRABLE','FAIL_HARD','REVIEW_REQUIRED')),
  overall_score double precision NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
  confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  unavailable_graders text[] NOT NULL DEFAULT ARRAY[]::text[],
  grader_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
  strengths jsonb NOT NULL DEFAULT '[]'::jsonb,
  repair_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL,
  UNIQUE (organization_id, quality_result_id),
  FOREIGN KEY (profile_id, profile_version) REFERENCES quality_profiles(profile_id, version),
  FOREIGN KEY (organization_id, artifact_id) REFERENCES artifacts(organization_id, id),
  FOREIGN KEY (organization_id, artifact_version_id) REFERENCES artifact_versions(organization_id, id)
);

CREATE TABLE IF NOT EXISTS quality_dimension_results (
  quality_result_id text NOT NULL REFERENCES quality_results(quality_result_id) ON DELETE CASCADE,
  dimension text NOT NULL CHECK (dimension IN ('CONSTRAINT_COMPLIANCE','COMPOSITION','VISUAL_HIERARCHY','ALIGNMENT_SPACING','TYPOGRAPHY_READABILITY','CONTRAST','BRAND_CONSISTENCY','IDENTITY_CONSISTENCY','TEXT_ACCURACY','LOGO_INTEGRITY','QR_READABILITY','IMAGE_DEFECTS','RESOLUTION_EXPORT_READINESS')),
  score double precision NOT NULL CHECK (score BETWEEN 0 AND 100),
  confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  threshold double precision NOT NULL CHECK (threshold BETWEEN 0 AND 100),
  weight double precision NOT NULL CHECK (weight >= 0),
  severity text NOT NULL CHECK (severity IN ('HARD','MAJOR','MINOR','ADVISORY')),
  hard_gate boolean NOT NULL,
  passed boolean NOT NULL,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (quality_result_id, dimension)
);

CREATE TABLE IF NOT EXISTS quality_violations (
  quality_result_id text NOT NULL REFERENCES quality_results(quality_result_id) ON DELETE CASCADE,
  violation_id text NOT NULL,
  dimension text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('HARD','MAJOR','MINOR','ADVISORY')),
  reason_code text NOT NULL,
  message text NOT NULL,
  target_id text NULL,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  repairable boolean NOT NULL,
  source_constraint jsonb NULL,
  PRIMARY KEY (quality_result_id, violation_id)
);

CREATE TABLE IF NOT EXISTS quality_evidence (
  quality_result_id text NOT NULL REFERENCES quality_results(quality_result_id) ON DELETE CASCADE,
  evidence_id text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('DETERMINISTIC','CONSTRAINT','BRAND','IDENTITY','OCR','QR','IMAGE_METADATA','VISUAL_GRADER','HUMAN_CALIBRATION')),
  source text NOT NULL,
  source_version text NOT NULL,
  confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  evidence_ref text NULL,
  data jsonb NULL,
  PRIMARY KEY (quality_result_id, evidence_id)
);

CREATE INDEX IF NOT EXISTS quality_results_artifact_idx ON quality_results (organization_id, artifact_version_id, created_at DESC);
CREATE INDEX IF NOT EXISTS quality_results_status_idx ON quality_results (organization_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS quality_violations_reason_idx ON quality_violations (reason_code, severity);
CREATE INDEX IF NOT EXISTS quality_calibration_lookup_idx ON quality_grader_calibrations (grader_id, grader_version, approved, created_at DESC);

CREATE OR REPLACE FUNCTION sync_artifact_quality_score_from_result()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE artifact_versions
     SET quality_score = NEW.overall_score / 100.0
   WHERE organization_id = NEW.organization_id
     AND id = NEW.artifact_version_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'quality result artifact version not found';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS quality_results_sync_artifact_score ON quality_results;
CREATE TRIGGER quality_results_sync_artifact_score
AFTER INSERT ON quality_results
FOR EACH ROW EXECUTE FUNCTION sync_artifact_quality_score_from_result();

-- QualityResult rows are append-only evidence. Application repositories must insert
-- result + dimensions + violations + evidence in one transaction. The critic never
-- changes artifact status; approval remains a separate policy/workflow decision.

COMMIT;
