ALTER TABLE audit_events
  ADD COLUMN IF NOT EXISTS session_ref VARCHAR(255),
  ADD COLUMN IF NOT EXISTS api_token_ref UUID,
  ADD COLUMN IF NOT EXISTS agent_run_ref UUID,
  ADD COLUMN IF NOT EXISTS task_ref UUID,
  ADD COLUMN IF NOT EXISTS resource_version INTEGER,
  ADD COLUMN IF NOT EXISTS result VARCHAR(16) DEFAULT 'SUCCESS' NOT NULL,
  ADD COLUMN IF NOT EXISTS reason_code VARCHAR(128),
  ADD COLUMN IF NOT EXISTS request_id VARCHAR(128),
  ADD COLUMN IF NOT EXISTS trace_id VARCHAR(128),
  ADD COLUMN IF NOT EXISTS security_metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
  ADD COLUMN IF NOT EXISTS change_summary_json JSONB DEFAULT '{}'::jsonb NOT NULL,
  ADD COLUMN IF NOT EXISTS retention_class VARCHAR(32) DEFAULT 'SECURITY_AUDIT' NOT NULL,
  ADD COLUMN IF NOT EXISTS retention_policy_version VARCHAR(64) DEFAULT 'technical-baseline-2026-08' NOT NULL,
  ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMP WITH TIME ZONE;

-- statement-breakpoint

UPDATE audit_events SET occurred_at = created_at WHERE occurred_at IS NULL;

-- statement-breakpoint

ALTER TABLE audit_events ALTER COLUMN occurred_at SET NOT NULL;

-- statement-breakpoint

ALTER TABLE audit_events
  ADD CONSTRAINT ck_audit_events_result
  CHECK (result IN ('SUCCESS','DENIED','FAILED'));

-- statement-breakpoint

ALTER TABLE audit_events
  ADD CONSTRAINT ck_audit_events_retention_class
  CHECK (retention_class IN ('SECURITY_AUDIT','BILLING','CONTENT','AGENT_TRACE','TEMP_SANDBOX','EXPORT','ANALYTICS'));

-- statement-breakpoint

ALTER TABLE audit_events
  ADD CONSTRAINT ck_audit_events_resource_version
  CHECK (resource_version IS NULL OR resource_version >= 0);

-- statement-breakpoint

ALTER TABLE audit_events
  ADD CONSTRAINT fk_audit_events_api_token_ref
  FOREIGN KEY (api_token_ref) REFERENCES api_tokens(id) ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE audit_events
  ADD CONSTRAINT fk_audit_events_agent_run_ref
  FOREIGN KEY (agent_run_ref) REFERENCES agent_runs(id) ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE audit_events
  ADD CONSTRAINT fk_audit_events_task_ref
  FOREIGN KEY (task_ref) REFERENCES tasks(id) ON DELETE SET NULL;

-- statement-breakpoint

CREATE INDEX ix_audit_events_org_occurred ON audit_events(organization_id, occurred_at DESC);

-- statement-breakpoint

CREATE INDEX ix_audit_events_org_actor_occurred ON audit_events(organization_id, actor_id, occurred_at DESC);

-- statement-breakpoint

CREATE INDEX ix_audit_events_org_action_occurred ON audit_events(organization_id, action, occurred_at DESC);

-- statement-breakpoint

CREATE INDEX ix_audit_events_org_resource_occurred ON audit_events(organization_id, subject_type, subject_id, occurred_at DESC);

-- statement-breakpoint

CREATE INDEX ix_audit_events_org_trace ON audit_events(organization_id, trace_id) WHERE trace_id IS NOT NULL;

-- statement-breakpoint

CREATE OR REPLACE FUNCTION governance_reject_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only';
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_audit_events_immutable
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION governance_reject_audit_mutation();

-- statement-breakpoint

CREATE TABLE governance_retention_policies (
  id UUID PRIMARY KEY,
  retention_class VARCHAR(32) NOT NULL,
  policy_version VARCHAR(64) NOT NULL,
  retain_days INTEGER NOT NULL,
  active BOOLEAN DEFAULT true NOT NULL,
  description TEXT NOT NULL,
  created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT ck_governance_retention_class CHECK (retention_class IN ('SECURITY_AUDIT','BILLING','CONTENT','AGENT_TRACE','TEMP_SANDBOX','EXPORT','ANALYTICS')),
  CONSTRAINT ck_governance_retention_days CHECK (retain_days >= 1),
  CONSTRAINT uq_governance_retention_policy UNIQUE (retention_class, policy_version)
);

-- statement-breakpoint

CREATE UNIQUE INDEX uq_governance_retention_active_class
ON governance_retention_policies(retention_class)
WHERE active = true;

-- statement-breakpoint

CREATE TABLE governance_legal_holds (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  hold_key VARCHAR(160) NOT NULL,
  scope_type VARCHAR(40) NOT NULL,
  scope_id VARCHAR(255) NOT NULL,
  reason TEXT NOT NULL,
  created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  released_by_user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
  released_at TIMESTAMP WITH TIME ZONE,
  release_reason TEXT,
  CONSTRAINT uq_governance_legal_hold_key UNIQUE (organization_id, hold_key),
  CONSTRAINT ck_governance_legal_hold_scope CHECK (scope_type IN ('ORGANIZATION','USER','PROJECT','ASSET','ARTIFACT','AUDIT')),
  CONSTRAINT ck_governance_legal_hold_reason CHECK (length(btrim(reason)) >= 8),
  CONSTRAINT ck_governance_legal_hold_release CHECK ((released_at IS NULL AND released_by_user_id IS NULL AND release_reason IS NULL) OR (released_at IS NOT NULL AND released_by_user_id IS NOT NULL AND release_reason IS NOT NULL AND length(btrim(release_reason)) >= 8))
);

-- statement-breakpoint

CREATE INDEX ix_governance_legal_hold_scope_active
ON governance_legal_holds(organization_id, scope_type, scope_id)
WHERE released_at IS NULL;

-- statement-breakpoint

CREATE TABLE governance_deletion_requests (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  subject_type VARCHAR(32) NOT NULL,
  subject_id VARCHAR(255) NOT NULL,
  status VARCHAR(32) DEFAULT 'IDENTIFIED' NOT NULL,
  requested_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  reason TEXT NOT NULL,
  scope_json JSONB DEFAULT '{}'::jsonb NOT NULL,
  hold_blockers_json JSONB DEFAULT '[]'::jsonb NOT NULL,
  object_gc_status VARCHAR(24) DEFAULT 'PENDING' NOT NULL,
  search_gc_status VARCHAR(24) DEFAULT 'PENDING' NOT NULL,
  requested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  completed_at TIMESTAMP WITH TIME ZONE,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  version INTEGER DEFAULT 1 NOT NULL,
  CONSTRAINT ck_governance_deletion_subject CHECK (subject_type IN ('USER','ORGANIZATION')),
  CONSTRAINT ck_governance_deletion_status CHECK (status IN ('IDENTIFIED','HOLD_BLOCKED','DEACTIVATED','ERASING','COMPLETED','FAILED')),
  CONSTRAINT ck_governance_gc_status CHECK (object_gc_status IN ('PENDING','BLOCKED','RUNNING','COMPLETED','FAILED') AND search_gc_status IN ('PENDING','BLOCKED','RUNNING','COMPLETED','FAILED')),
  CONSTRAINT ck_governance_deletion_reason CHECK (length(btrim(reason)) >= 8)
);

-- statement-breakpoint

CREATE INDEX ix_governance_deletion_org_status ON governance_deletion_requests(organization_id, status, requested_at DESC);

-- statement-breakpoint

CREATE TABLE governance_audit_exports (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  requested_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  export_format VARCHAR(8) NOT NULL,
  filters_json JSONB DEFAULT '{}'::jsonb NOT NULL,
  status VARCHAR(24) DEFAULT 'PENDING' NOT NULL,
  result_ref TEXT,
  requested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  completed_at TIMESTAMP WITH TIME ZONE,
  CONSTRAINT ck_governance_audit_export_format CHECK (export_format IN ('JSON','CSV')),
  CONSTRAINT ck_governance_audit_export_status CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED'))
);

-- statement-breakpoint

CREATE INDEX ix_governance_audit_export_org_requested ON governance_audit_exports(organization_id, requested_at DESC);

-- statement-breakpoint

INSERT INTO governance_retention_policies(id,retention_class,policy_version,retain_days,active,description,created_at) VALUES
('00000000-0000-7000-8000-000000000651','SECURITY_AUDIT','technical-baseline-2026-08',2555,true,'Technical baseline; legal review required before jurisdictional launch.',now()),
('00000000-0000-7000-8000-000000000652','BILLING','technical-baseline-2026-08',2555,true,'Technical baseline; legal review required before jurisdictional launch.',now()),
('00000000-0000-7000-8000-000000000653','CONTENT','technical-baseline-2026-08',365,true,'Technical baseline; legal review required before jurisdictional launch.',now()),
('00000000-0000-7000-8000-000000000654','AGENT_TRACE','technical-baseline-2026-08',90,true,'Technical baseline; legal review required before jurisdictional launch.',now()),
('00000000-0000-7000-8000-000000000655','TEMP_SANDBOX','technical-baseline-2026-08',7,true,'Technical baseline; legal review required before jurisdictional launch.',now()),
('00000000-0000-7000-8000-000000000656','EXPORT','technical-baseline-2026-08',30,true,'Technical baseline; legal review required before jurisdictional launch.',now()),
('00000000-0000-7000-8000-000000000657','ANALYTICS','technical-baseline-2026-08',365,true,'Technical baseline; legal review required before jurisdictional launch.',now());
