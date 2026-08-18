CREATE TABLE approval_requests (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    agent_run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    approval_type VARCHAR(40) NOT NULL,
    subject_type VARCHAR(80) NOT NULL,
    subject_id UUID NOT NULL,
    subject_version_ref VARCHAR(160) NOT NULL,
    subject_snapshot_hash VARCHAR(64),
    artifact_version_id UUID REFERENCES artifact_versions(id) ON DELETE RESTRICT,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    requested_by VARCHAR(200) NOT NULL,
    required_permission VARCHAR(120) NOT NULL,
    policy_mode VARCHAR(32) NOT NULL DEFAULT 'ANY_ONE',
    policy_version INTEGER NOT NULL DEFAULT 1,
    min_approvals INTEGER NOT NULL DEFAULT 1,
    payload_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    changes_requested_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    superseded_by_id UUID REFERENCES approval_requests(id) ON DELETE SET NULL,
    interrupt_id VARCHAR(200),
    resume_version INTEGER,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT ck_approval_requests_status CHECK (
        status IN ('PENDING','APPROVED','REJECTED','CHANGES_REQUESTED','EXPIRED','CANCELLED','SUPERSEDED')
    ),
    CONSTRAINT ck_approval_requests_type CHECK (
        approval_type IN ('CREATIVE_DIRECTION','ARTIFACT_VERSION','BRAND_RULE_SET','BUDGET_INCREASE','EXTERNAL_PUBLISH','DESTRUCTIVE_ACTION','CUSTOM_REVIEW')
    ),
    CONSTRAINT ck_approval_requests_policy_mode CHECK (
        policy_mode IN ('ANY_ONE','ALL','MIN_N','ROLE_BASED_SEQUENCE')
    ),
    CONSTRAINT ck_approval_requests_policy_numbers CHECK (policy_version >= 1 AND min_approvals >= 1),
    CONSTRAINT ck_approval_requests_snapshot_hash CHECK (
        subject_snapshot_hash IS NULL OR subject_snapshot_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_approval_requests_bridge_pair CHECK (
        (interrupt_id IS NULL AND resume_version IS NULL)
        OR (interrupt_id IS NOT NULL AND resume_version IS NOT NULL AND resume_version >= 0)
    ),
    CONSTRAINT ck_approval_requests_artifact_exact_subject CHECK (
        approval_type <> 'ARTIFACT_VERSION'
        OR (artifact_version_id IS NOT NULL AND subject_id = artifact_version_id AND subject_snapshot_hash IS NOT NULL)
    )
);

-- statement-breakpoint

CREATE INDEX ix_approval_requests_project_status
ON approval_requests (organization_id, project_id, status, created_at DESC);

-- statement-breakpoint

CREATE INDEX ix_approval_requests_subject
ON approval_requests (organization_id, subject_type, subject_id, created_at DESC);

-- statement-breakpoint

CREATE UNIQUE INDEX uq_approval_requests_pending_artifact
ON approval_requests (organization_id, artifact_version_id)
WHERE approval_type='ARTIFACT_VERSION' AND status='PENDING';

-- statement-breakpoint

CREATE TABLE approval_decisions (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    approval_id UUID NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE,
    operation_id UUID NOT NULL,
    decision VARCHAR(32) NOT NULL,
    actor_id VARCHAR(200) NOT NULL,
    reason TEXT,
    feedback_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    approval_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_approval_decision_operation UNIQUE (organization_id, operation_id),
    CONSTRAINT uq_approval_decision_actor UNIQUE (approval_id, actor_id),
    CONSTRAINT ck_approval_decisions_decision CHECK (
        decision IN ('APPROVED','REJECTED','CHANGES_REQUESTED')
    ),
    CONSTRAINT ck_approval_decisions_version CHECK (approval_version >= 1)
);

-- statement-breakpoint

CREATE INDEX ix_approval_decisions_approval_created
ON approval_decisions (approval_id, created_at);

-- statement-breakpoint

CREATE TABLE approval_audit_events (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    approval_id UUID NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    actor_id VARCHAR(200),
    status_from VARCHAR(32),
    status_to VARCHAR(32),
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

-- statement-breakpoint

CREATE INDEX ix_approval_audit_events_approval_created
ON approval_audit_events (approval_id, created_at, id);

-- statement-breakpoint

CREATE TABLE approval_effects (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    approval_id UUID NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE,
    effect_type VARCHAR(48) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    operation_id UUID NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_approval_effect_type UNIQUE (approval_id, effect_type),
    CONSTRAINT uq_approval_effect_operation UNIQUE (organization_id, operation_id),
    CONSTRAINT ck_approval_effects_type CHECK (
        effect_type IN ('ARTIFACT_VERSION_APPROVE','AGENT_RUN_RESUME')
    ),
    CONSTRAINT ck_approval_effects_status CHECK (
        status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')
    ),
    CONSTRAINT ck_approval_effects_attempt_count CHECK (attempt_count >= 0)
);

-- statement-breakpoint

CREATE INDEX ix_approval_effects_pending
ON approval_effects (organization_id, status, created_at)
WHERE status IN ('PENDING','FAILED');
