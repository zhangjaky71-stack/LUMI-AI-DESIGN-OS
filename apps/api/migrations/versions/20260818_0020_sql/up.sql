CREATE TABLE repair_policy_snapshots (
  policy_id VARCHAR(200) NOT NULL,
  version INTEGER NOT NULL,
  policy_hash VARCHAR(64) NOT NULL,
  policy_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (policy_id, version),
  CONSTRAINT uq_repair_policy_hash UNIQUE (policy_hash),
  CONSTRAINT ck_repair_policy_version CHECK (version >= 1),
  CONSTRAINT ck_repair_policy_hash CHECK (policy_hash ~ '^[0-9a-f]{64}$')
);

-- statement-breakpoint

CREATE TABLE auto_repair_jobs (
  repair_job_id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  requested_by VARCHAR(200) NOT NULL,
  source_artifact_id UUID NOT NULL REFERENCES artifacts(id) ON DELETE RESTRICT,
  source_artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  source_quality_result_id UUID NOT NULL REFERENCES artifact_quality_results(quality_result_id) ON DELETE RESTRICT,
  original_branch_id UUID NOT NULL REFERENCES artifact_branches(id) ON DELETE RESTRICT,
  original_head_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  working_artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  current_quality_result_id UUID NOT NULL REFERENCES artifact_quality_results(quality_result_id) ON DELETE RESTRICT,
  policy_id VARCHAR(200) NOT NULL,
  policy_version INTEGER NOT NULL,
  policy_hash VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  spent_usd NUMERIC(20,8) NOT NULL DEFAULT 0,
  final_artifact_version_id UUID REFERENCES artifact_versions(id) ON DELETE SET NULL,
  semantic_hash VARCHAR(64) NOT NULL,
  job_json JSONB NOT NULL,
  reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_auto_repair_operation UNIQUE (organization_id, operation_id),
  CONSTRAINT fk_auto_repair_policy FOREIGN KEY (policy_id, policy_version)
    REFERENCES repair_policy_snapshots(policy_id, version) ON DELETE RESTRICT,
  CONSTRAINT ck_auto_repair_hashes CHECK (
    policy_hash ~ '^[0-9a-f]{64}$' AND semantic_hash ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT ck_auto_repair_status CHECK (
    status IN ('PLANNED','RUNNING','READY','REVIEW_REQUIRED','FAILED','BUDGET_EXHAUSTED','STALE_CONFLICT','CANCELLED')
  ),
  CONSTRAINT ck_auto_repair_spend CHECK (spent_usd >= 0)
);

-- statement-breakpoint

CREATE INDEX ix_auto_repair_jobs_source
ON auto_repair_jobs (organization_id, source_artifact_version_id, created_at);

-- statement-breakpoint

CREATE INDEX ix_auto_repair_jobs_status
ON auto_repair_jobs (organization_id, status, updated_at);

-- statement-breakpoint

CREATE TABLE auto_repair_attempts (
  repair_job_id UUID NOT NULL REFERENCES auto_repair_jobs(repair_job_id) ON DELETE CASCADE,
  iteration INTEGER NOT NULL,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  source_artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  before_quality_result_id UUID NOT NULL REFERENCES artifact_quality_results(quality_result_id) ON DELETE RESTRICT,
  repair_kind VARCHAR(40) NOT NULL,
  decision VARCHAR(48) NOT NULL,
  estimated_cost_usd NUMERIC(20,8) NOT NULL DEFAULT 0,
  actual_cost_usd NUMERIC(20,8) NOT NULL DEFAULT 0,
  reservation_id VARCHAR(200),
  candidate_artifact_version_id UUID REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  after_quality_result_id UUID REFERENCES artifact_quality_results(quality_result_id) ON DELETE RESTRICT,
  before_score NUMERIC(8,4) NOT NULL,
  after_score NUMERIC(8,4),
  score_delta NUMERIC(8,4),
  attempt_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (repair_job_id, iteration),
  CONSTRAINT ck_auto_repair_iteration CHECK (iteration >= 1 AND iteration <= 3),
  CONSTRAINT ck_auto_repair_kind CHECK (
    repair_kind IN ('STRUCTURAL_DESIGN_OP','LOCAL_IMAGE_EDIT','REGENERATE_ELEMENT','REGENERATE_ARTIFACT','COPY_TYPOGRAPHY_FIX','MANUAL_REVIEW')
  ),
  CONSTRAINT ck_auto_repair_costs CHECK (estimated_cost_usd >= 0 AND actual_cost_usd >= 0),
  CONSTRAINT ck_auto_repair_scores CHECK (
    before_score >= 0 AND before_score <= 100
    AND (after_score IS NULL OR (after_score >= 0 AND after_score <= 100))
  )
);

-- statement-breakpoint

CREATE TABLE repair_learning_signals (
  learning_signal_id UUID PRIMARY KEY,
  repair_job_id UUID NOT NULL REFERENCES auto_repair_jobs(repair_job_id) ON DELETE CASCADE,
  iteration INTEGER NOT NULL,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  source_artifact_version_id UUID NOT NULL REFERENCES artifact_versions(id) ON DELETE RESTRICT,
  candidate_artifact_version_id UUID REFERENCES artifact_versions(id) ON DELETE SET NULL,
  source_quality_result_id UUID NOT NULL REFERENCES artifact_quality_results(quality_result_id) ON DELETE RESTRICT,
  candidate_quality_result_id UUID REFERENCES artifact_quality_results(quality_result_id) ON DELETE SET NULL,
  repair_kind VARCHAR(40) NOT NULL,
  violation_codes JSONB NOT NULL,
  action_json JSONB NOT NULL,
  before_score NUMERIC(8,4) NOT NULL,
  after_score NUMERIC(8,4),
  human_decision VARCHAR(24),
  human_decision_by VARCHAR(200),
  human_decision_at TIMESTAMPTZ,
  eligible_for_training BOOLEAN NOT NULL DEFAULT FALSE,
  governance_approval_ref VARCHAR(240),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT fk_repair_learning_attempt FOREIGN KEY (repair_job_id, iteration)
    REFERENCES auto_repair_attempts(repair_job_id, iteration) ON DELETE CASCADE,
  CONSTRAINT ck_repair_learning_human_decision CHECK (
    human_decision IS NULL OR human_decision IN ('ACCEPTED','REJECTED')
  ),
  CONSTRAINT ck_repair_learning_training_governance CHECK (
    eligible_for_training = FALSE OR governance_approval_ref IS NOT NULL
  )
);
