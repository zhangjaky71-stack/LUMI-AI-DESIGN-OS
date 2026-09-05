BEGIN;

CREATE TABLE IF NOT EXISTS auto_repair_policies (
  policy_id text NOT NULL,
  version text NOT NULL,
  max_auto_repair_iterations integer NOT NULL CHECK (max_auto_repair_iterations BETWEEN 1 AND 10),
  max_repair_cost_usd numeric(18,6) NOT NULL CHECK (max_repair_cost_usd >= 0),
  minimum_expected_gain double precision NOT NULL CHECK (minimum_expected_gain >= 0 AND minimum_expected_gain <= 100),
  max_score_regression double precision NOT NULL CHECK (max_score_regression >= 0 AND max_score_regression <= 100),
  status text NOT NULL DEFAULT 'PUBLISHED' CHECK (status IN ('DRAFT','PUBLISHED','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (policy_id, version)
);

INSERT INTO auto_repair_policies (
  policy_id, version, max_auto_repair_iterations, max_repair_cost_usd,
  minimum_expected_gain, max_score_regression, status
) VALUES
  ('repair-policy:exploration','1.0.0',2,0.500000,3,5,'PUBLISHED'),
  ('repair-policy:production-web','1.0.0',3,2.000000,5,2,'PUBLISHED'),
  ('repair-policy:brand-strict','1.0.0',3,2.000000,5,1,'PUBLISHED'),
  ('repair-policy:product-strict','1.0.0',3,3.000000,5,1,'PUBLISHED'),
  ('repair-policy:print','1.0.0',3,2.000000,5,1,'PUBLISHED'),
  ('repair-policy:social-fast','1.0.0',2,1.000000,4,3,'PUBLISHED')
ON CONFLICT (policy_id, version) DO NOTHING;

CREATE TABLE IF NOT EXISTS auto_repair_loops (
  loop_id text PRIMARY KEY CHECK (loop_id LIKE 'repair-loop:%'),
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  artifact_id uuid NOT NULL,
  branch_id uuid NOT NULL,
  source_artifact_version_id uuid NOT NULL,
  source_quality_result_id text NOT NULL,
  policy_id text NOT NULL,
  policy_version text NOT NULL,
  status text NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','REVIEW_REQUIRED','BUDGET_EXHAUSTED','ITERATION_LIMIT','STALE_SOURCE','NO_SAFE_REPAIR','FAILED')),
  iteration_count integer NOT NULL DEFAULT 0 CHECK (iteration_count BETWEEN 0 AND 10),
  spent_usd numeric(18,6) NOT NULL DEFAULT 0 CHECK (spent_usd >= 0),
  final_artifact_version_id uuid NULL,
  final_quality_result_id text NULL,
  reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  UNIQUE (organization_id, loop_id),
  FOREIGN KEY (policy_id, policy_version) REFERENCES auto_repair_policies(policy_id, version),
  FOREIGN KEY (organization_id, artifact_id) REFERENCES artifacts(organization_id, id),
  FOREIGN KEY (organization_id, branch_id) REFERENCES artifact_branches(organization_id, id),
  FOREIGN KEY (organization_id, source_artifact_version_id) REFERENCES artifact_versions(organization_id, id),
  FOREIGN KEY (source_quality_result_id) REFERENCES quality_results(quality_result_id),
  FOREIGN KEY (organization_id, final_artifact_version_id) REFERENCES artifact_versions(organization_id, id),
  FOREIGN KEY (final_quality_result_id) REFERENCES quality_results(quality_result_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS auto_repair_active_source_idx
  ON auto_repair_loops (organization_id, branch_id, source_artifact_version_id, policy_id, policy_version)
  WHERE status = 'RUNNING';

CREATE TABLE IF NOT EXISTS auto_repair_attempts (
  loop_id text NOT NULL REFERENCES auto_repair_loops(loop_id) ON DELETE CASCADE,
  iteration integer NOT NULL CHECK (iteration BETWEEN 1 AND 10),
  plan_item_id text NOT NULL,
  action_kind text NOT NULL CHECK (action_kind IN ('STRUCTURAL_DESIGN_OP','LOCAL_IMAGE_EDIT','REGENERATE_ELEMENT','REGENERATE_ARTIFACT','RESOLUTION_UPSCALE','MANUAL_REVIEW')),
  fingerprint char(64) NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
  source_artifact_version_id uuid NOT NULL,
  candidate_artifact_version_id uuid NULL,
  source_quality_result_id text NOT NULL,
  candidate_quality_result_id text NULL,
  before_score double precision NOT NULL CHECK (before_score BETWEEN 0 AND 100),
  after_score double precision NULL CHECK (after_score IS NULL OR after_score BETWEEN 0 AND 100),
  score_gain double precision NULL CHECK (score_gain IS NULL OR score_gain BETWEEN -100 AND 100),
  estimated_cost_usd numeric(18,6) NOT NULL CHECK (estimated_cost_usd >= 0),
  actual_cost_usd numeric(18,6) NOT NULL DEFAULT 0 CHECK (actual_cost_usd >= 0),
  disposition text NOT NULL CHECK (disposition IN ('PLANNED','PROMOTED_READY','PROMOTED_DRAFT','REJECTED','REVIEW')),
  reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  PRIMARY KEY (loop_id, iteration, plan_item_id),
  UNIQUE (loop_id, fingerprint),
  FOREIGN KEY (source_quality_result_id) REFERENCES quality_results(quality_result_id),
  FOREIGN KEY (candidate_quality_result_id) REFERENCES quality_results(quality_result_id),
  FOREIGN KEY (candidate_artifact_version_id) REFERENCES artifact_versions(id)
);

CREATE INDEX IF NOT EXISTS auto_repair_attempt_candidate_idx
  ON auto_repair_attempts (candidate_artifact_version_id)
  WHERE candidate_artifact_version_id IS NOT NULL;

CREATE OR REPLACE FUNCTION promote_auto_repair_candidate(
  p_organization_id uuid,
  p_loop_id text,
  p_candidate_version_id uuid,
  p_expected_branch_head uuid,
  p_target_status text,
  p_quality_result_id text
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  v_branch_id uuid;
  v_artifact_id uuid;
  v_quality_score double precision;
  v_source_version_id uuid;
BEGIN
  IF p_target_status NOT IN ('DRAFT','READY') THEN
    RAISE EXCEPTION 'AUTO_REPAIR_INVALID_PROMOTION_STATUS';
  END IF;

  SELECT l.branch_id, l.artifact_id
    INTO v_branch_id, v_artifact_id
    FROM auto_repair_loops l
   WHERE l.loop_id = p_loop_id
     AND l.organization_id = p_organization_id
     AND l.status = 'RUNNING'
   FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'AUTO_REPAIR_LOOP_NOT_RUNNING'; END IF;

  SELECT q.overall_score / 100.0
    INTO v_quality_score
    FROM quality_results q
   WHERE q.quality_result_id = p_quality_result_id
     AND q.organization_id = p_organization_id
     AND q.artifact_version_id = p_candidate_version_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'AUTO_REPAIR_CANDIDATE_QUALITY_MISMATCH'; END IF;

  SELECT v.parent_version_id
    INTO v_source_version_id
    FROM artifact_versions v
   WHERE v.id = p_candidate_version_id
     AND v.organization_id = p_organization_id
     AND v.artifact_id = v_artifact_id
     AND v.branch_id = v_branch_id
     AND v.status = 'DRAFT'
   FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'AUTO_REPAIR_CANDIDATE_NOT_DRAFT'; END IF;
  IF v_source_version_id IS DISTINCT FROM p_expected_branch_head THEN
    RAISE EXCEPTION 'AUTO_REPAIR_CANDIDATE_SOURCE_MISMATCH';
  END IF;

  UPDATE artifact_branches
     SET head_version_id = p_candidate_version_id
   WHERE organization_id = p_organization_id
     AND id = v_branch_id
     AND artifact_id = v_artifact_id
     AND head_version_id IS NOT DISTINCT FROM p_expected_branch_head;
  IF NOT FOUND THEN RAISE EXCEPTION 'AUTO_REPAIR_BRANCH_HEAD_CAS_CONFLICT'; END IF;

  UPDATE artifact_versions
     SET status = p_target_status,
         quality_score = v_quality_score
   WHERE organization_id = p_organization_id
     AND id = p_candidate_version_id;
END;
$$;

-- Production candidate persistence contract:
-- 1. INSERT a new artifact_versions row with status='DRAFT' and parent_version_id equal
--    to the exact source branch head. DO NOT mutate artifact_branches at insert time.
-- 2. INSERT artifact_edges type='EDITED_FROM' with repair_loop_id/plan_item_id metadata.
-- 3. Re-evaluate the exact candidate through NODE-50 and persist QualityResult.
-- 4. Only then call promote_auto_repair_candidate(...). Its CAS prevents a concurrent
--    user/agent edit from being overwritten. Any raised exception leaves the candidate off-head.
-- 5. Rejected/review candidates remain immutable audit evidence and must never be promoted.
-- Paid repair reservations/actual cost remain owned by NODE-27. These tables only reference
-- repair cost facts; they are not a second financial ledger.

COMMIT;
