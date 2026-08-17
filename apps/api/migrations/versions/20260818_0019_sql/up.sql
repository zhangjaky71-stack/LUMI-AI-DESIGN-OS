CREATE TABLE quality_profile_snapshots (
  profile_id VARCHAR(200) NOT NULL,
  version INTEGER NOT NULL,
  profile_key VARCHAR(80) NOT NULL,
  profile_hash VARCHAR(64) NOT NULL,
  profile_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, version),
  CONSTRAINT uq_quality_profile_hash UNIQUE (profile_hash),
  CONSTRAINT ck_quality_profile_version CHECK (version >= 1),
  CONSTRAINT ck_quality_profile_hash CHECK (profile_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_quality_profile_key CHECK (
    profile_key IN ('exploration','production-web','brand-strict','product-strict','print','social-fast')
  )
);

-- statement-breakpoint

CREATE TABLE quality_grader_calibrations (
  calibration_id VARCHAR(200) PRIMARY KEY,
  grader_id VARCHAR(200) NOT NULL,
  provider VARCHAR(120),
  model VARCHAR(200),
  model_revision VARCHAR(200),
  dataset_hash VARCHAR(64) NOT NULL,
  threshold_version INTEGER NOT NULL,
  sample_count INTEGER NOT NULL,
  precision NUMERIC(8,6),
  recall NUMERIC(8,6),
  false_positive_rate NUMERIC(8,6),
  false_negative_rate NUMERIC(8,6),
  inter_rater_agreement NUMERIC(8,6),
  calibration_hash VARCHAR(64) NOT NULL,
  is_current BOOLEAN NOT NULL DEFAULT FALSE,
  calibration_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_quality_calibration_hash UNIQUE (calibration_hash),
  CONSTRAINT ck_quality_calibration_hash CHECK (calibration_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_quality_calibration_dataset_hash CHECK (dataset_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_quality_calibration_counts CHECK (threshold_version >= 1 AND sample_count >= 1),
  CONSTRAINT ck_quality_calibration_metrics CHECK (
    (precision IS NULL OR (precision >= 0 AND precision <= 1))
    AND (recall IS NULL OR (recall >= 0 AND recall <= 1))
    AND (false_positive_rate IS NULL OR (false_positive_rate >= 0 AND false_positive_rate <= 1))
    AND (false_negative_rate IS NULL OR (false_negative_rate >= 0 AND false_negative_rate <= 1))
    AND (inter_rater_agreement IS NULL OR (inter_rater_agreement >= 0 AND inter_rater_agreement <= 1))
  )
);

-- statement-breakpoint

CREATE UNIQUE INDEX uq_quality_current_grader
ON quality_grader_calibrations (grader_id)
WHERE is_current = TRUE;

-- statement-breakpoint

CREATE TABLE artifact_quality_results (
  quality_result_id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  artifact_id UUID NOT NULL REFERENCES artifacts(id) ON DELETE RESTRICT,
  artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  artifact_content_hash VARCHAR(64) NOT NULL,
  profile_id VARCHAR(200) NOT NULL,
  profile_version INTEGER NOT NULL,
  profile_hash VARCHAR(64) NOT NULL,
  gate_status VARCHAR(32) NOT NULL,
  overall_score NUMERIC(8,4) NOT NULL,
  overall_confidence NUMERIC(8,6) NOT NULL,
  critic_grader_id VARCHAR(200),
  critic_calibration_id VARCHAR(200) REFERENCES quality_grader_calibrations(calibration_id) ON DELETE RESTRICT,
  critic_calibration_hash VARCHAR(64),
  result_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_artifact_quality_operation UNIQUE (organization_id, operation_id),
  CONSTRAINT fk_artifact_quality_profile FOREIGN KEY (profile_id, profile_version)
    REFERENCES quality_profile_snapshots(profile_id, version) ON DELETE RESTRICT,
  CONSTRAINT ck_artifact_quality_hashes CHECK (
    artifact_content_hash ~ '^[0-9a-f]{64}$'
    AND profile_hash ~ '^[0-9a-f]{64}$'
    AND (critic_calibration_hash IS NULL OR critic_calibration_hash ~ '^[0-9a-f]{64}$')
  ),
  CONSTRAINT ck_artifact_quality_gate_status CHECK (
    gate_status IN ('PASS','PASS_WITH_WARNINGS','FAIL_REPAIRABLE','FAIL_HARD','REVIEW_REQUIRED')
  ),
  CONSTRAINT ck_artifact_quality_score CHECK (
    overall_score >= 0 AND overall_score <= 100
    AND overall_confidence >= 0 AND overall_confidence <= 1
  )
);

-- statement-breakpoint

CREATE INDEX ix_artifact_quality_version
ON artifact_quality_results (organization_id, artifact_version_id, created_at);

-- statement-breakpoint

CREATE TABLE quality_dimension_assessments (
  quality_result_id UUID NOT NULL REFERENCES artifact_quality_results(quality_result_id) ON DELETE CASCADE,
  dimension VARCHAR(80) NOT NULL,
  score NUMERIC(8,4) NOT NULL,
  confidence NUMERIC(8,6) NOT NULL,
  threshold NUMERIC(8,4) NOT NULL,
  severity VARCHAR(16) NOT NULL,
  grader_id VARCHAR(200),
  assessment_json JSONB NOT NULL,
  PRIMARY KEY (quality_result_id, dimension),
  CONSTRAINT ck_quality_dimension_score CHECK (
    score >= 0 AND score <= 100 AND threshold >= 0 AND threshold <= 100
    AND confidence >= 0 AND confidence <= 1
  ),
  CONSTRAINT ck_quality_dimension_severity CHECK (severity IN ('INFO','WARNING','ERROR','HARD'))
);

-- statement-breakpoint

CREATE TABLE quality_violations (
  quality_result_id UUID NOT NULL REFERENCES artifact_quality_results(quality_result_id) ON DELETE CASCADE,
  violation_id VARCHAR(240) NOT NULL,
  dimension VARCHAR(80) NOT NULL,
  code VARCHAR(200) NOT NULL,
  severity VARCHAR(16) NOT NULL,
  confidence NUMERIC(8,6) NOT NULL,
  blocking BOOLEAN NOT NULL DEFAULT FALSE,
  violation_json JSONB NOT NULL,
  PRIMARY KEY (quality_result_id, violation_id),
  CONSTRAINT ck_quality_violation_confidence CHECK (confidence >= 0 AND confidence <= 1),
  CONSTRAINT ck_quality_violation_severity CHECK (severity IN ('INFO','WARNING','ERROR','HARD')),
  CONSTRAINT ck_quality_hard_blocks CHECK (severity <> 'HARD' OR blocking = TRUE)
);
