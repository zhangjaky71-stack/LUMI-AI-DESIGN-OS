ALTER TABLE artifact_provenance
    ADD COLUMN agent_run_id UUID,
    ADD COLUMN task_id UUID,
    ADD COLUMN generation_id UUID,
    ADD COLUMN provider VARCHAR(80),
    ADD COLUMN model VARCHAR(160),
    ADD COLUMN provider_request_id VARCHAR(255),
    ADD COLUMN prompt_hash VARCHAR(64),
    ADD COLUMN prompt_template_version VARCHAR(120),
    ADD COLUMN recipe_version VARCHAR(120),
    ADD COLUMN compiler_version VARCHAR(120),
    ADD COLUMN agent_version VARCHAR(120),
    ADD COLUMN code_git_sha VARCHAR(64),
    ADD COLUMN constraint_snapshot_hash VARCHAR(64),
    ADD COLUMN completeness_status VARCHAR(32) NOT NULL DEFAULT 'PARTIAL',
    ADD COLUMN completeness_score NUMERIC(8, 5) NOT NULL DEFAULT 0,
    ADD COLUMN missing_fields_json JSONB NOT NULL DEFAULT '[]'::jsonb;

-- statement-breakpoint

ALTER TABLE artifact_provenance
    ADD CONSTRAINT ck_artifact_provenance_completeness_status
    CHECK (completeness_status IN ('FULLY_TRACEABLE','PARTIAL')),
    ADD CONSTRAINT ck_artifact_provenance_completeness_score
    CHECK (completeness_score >= 0 AND completeness_score <= 1),
    ADD CONSTRAINT ck_artifact_provenance_prompt_hash
    CHECK (prompt_hash IS NULL OR prompt_hash ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT ck_artifact_provenance_constraint_hash
    CHECK (constraint_snapshot_hash IS NULL OR constraint_snapshot_hash ~ '^[0-9a-f]{64}$');

-- statement-breakpoint

CREATE INDEX ix_artifact_provenance_agent_run_id ON artifact_provenance(agent_run_id);

-- statement-breakpoint

CREATE INDEX ix_artifact_provenance_task_id ON artifact_provenance(task_id);

-- statement-breakpoint

CREATE INDEX ix_artifact_provenance_generation_id ON artifact_provenance(generation_id);

-- statement-breakpoint

CREATE INDEX ix_artifact_provenance_provider_model ON artifact_provenance(provider, model);

-- statement-breakpoint

CREATE INDEX ix_artifact_provenance_prompt_hash ON artifact_provenance(prompt_hash);

-- statement-breakpoint

CREATE TABLE artifact_version_approvals (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    artifact_version_id UUID NOT NULL,
    approved_by_id VARCHAR(200) NOT NULL,
    approved_at TIMESTAMP WITH TIME ZONE NOT NULL,
    validation_ref TEXT NOT NULL,
    CONSTRAINT pk_artifact_version_approvals PRIMARY KEY(id),
    CONSTRAINT uq_artifact_version_approval UNIQUE(artifact_version_id),
    CONSTRAINT fk_artifact_version_approvals_organization
        FOREIGN KEY(organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_artifact_version_approvals_version
        FOREIGN KEY(artifact_version_id) REFERENCES artifact_versions(id) ON DELETE CASCADE
);

-- statement-breakpoint

CREATE INDEX ix_artifact_version_approvals_organization_id
    ON artifact_version_approvals(organization_id);

-- statement-breakpoint

CREATE TABLE artifact_gc_marks (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    bucket VARCHAR(128) NOT NULL,
    object_key TEXT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    marked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    not_before TIMESTAMP WITH TIME ZONE NOT NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'MARKED',
    completed_at TIMESTAMP WITH TIME ZONE,
    reason VARCHAR(500),
    CONSTRAINT pk_artifact_gc_marks PRIMARY KEY(id),
    CONSTRAINT ck_artifact_gc_marks_state CHECK (state IN ('MARKED','CANCELLED','DELETED')),
    CONSTRAINT ck_artifact_gc_marks_checksum CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_artifact_gc_marks_organization
        FOREIGN KEY(organization_id) REFERENCES organizations(id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE UNIQUE INDEX uq_artifact_gc_active_mark
    ON artifact_gc_marks(organization_id, bucket, object_key)
    WHERE state = 'MARKED';

-- statement-breakpoint

CREATE INDEX ix_artifact_gc_marks_pending
    ON artifact_gc_marks(organization_id, state, not_before);

-- statement-breakpoint

CREATE TABLE artifact_gc_audits (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    gc_mark_id UUID NOT NULL,
    action VARCHAR(80) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    bucket VARCHAR(128) NOT NULL,
    object_key TEXT NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    detail VARCHAR(500),
    CONSTRAINT pk_artifact_gc_audits PRIMARY KEY(id),
    CONSTRAINT fk_artifact_gc_audits_organization
        FOREIGN KEY(organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_artifact_gc_audits_mark
        FOREIGN KEY(gc_mark_id) REFERENCES artifact_gc_marks(id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_artifact_gc_audits_mark ON artifact_gc_audits(gc_mark_id);

-- statement-breakpoint

CREATE TABLE artifact_outbox_events (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version_id UUID,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_at TIMESTAMP WITH TIME ZONE,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    CONSTRAINT pk_artifact_outbox_events PRIMARY KEY(id),
    CONSTRAINT ck_artifact_outbox_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT fk_artifact_outbox_events_organization
        FOREIGN KEY(organization_id) REFERENCES organizations(id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_artifact_outbox_events_pending
    ON artifact_outbox_events(published_at, occurred_at)
    WHERE published_at IS NULL;
