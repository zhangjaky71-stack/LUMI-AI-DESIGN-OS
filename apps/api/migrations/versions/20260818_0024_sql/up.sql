CREATE TABLE platform_admin_principals (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(40) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  granted_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  version INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT uq_platform_admin_principal_user UNIQUE(user_id),
  CONSTRAINT ck_platform_admin_role CHECK (role IN ('SUPPORT_READ','OPS','BILLING_ADMIN','AI_CONFIG_ADMIN','SECURITY_ADMIN','SUPER_ADMIN')),
  CONSTRAINT ck_platform_admin_reason CHECK (length(btrim(reason)) >= 8)
);

-- statement-breakpoint

CREATE INDEX ix_platform_admin_principal_role_active ON platform_admin_principals(role, active);

-- statement-breakpoint

CREATE TABLE platform_admin_audit_events (
  id UUID PRIMARY KEY,
  actor_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  actor_role VARCHAR(40) NOT NULL,
  action VARCHAR(120) NOT NULL,
  resource_type VARCHAR(80) NOT NULL,
  resource_id VARCHAR(255),
  target_organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
  reason TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_platform_admin_audit_role CHECK (actor_role IN ('SUPPORT_READ','OPS','BILLING_ADMIN','AI_CONFIG_ADMIN','SECURITY_ADMIN','SUPER_ADMIN'))
);

-- statement-breakpoint

CREATE INDEX ix_platform_admin_audit_created ON platform_admin_audit_events(created_at DESC);

-- statement-breakpoint

CREATE INDEX ix_platform_admin_audit_actor_created ON platform_admin_audit_events(actor_user_id, created_at DESC);

-- statement-breakpoint

CREATE INDEX ix_platform_admin_audit_resource ON platform_admin_audit_events(resource_type, resource_id, created_at DESC);

-- statement-breakpoint

CREATE TABLE platform_feature_flags (
  id UUID PRIMARY KEY,
  flag_key VARCHAR(160) NOT NULL,
  scope VARCHAR(24) NOT NULL,
  target_id VARCHAR(255),
  value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  owner VARCHAR(160) NOT NULL,
  reason TEXT NOT NULL,
  security_locked BOOLEAN NOT NULL DEFAULT false,
  expires_at TIMESTAMPTZ,
  created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  updated_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  version INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT ck_platform_feature_flag_scope CHECK (scope IN ('global','organization','user')),
  CONSTRAINT ck_platform_feature_flag_target CHECK ((scope='global' AND target_id IS NULL) OR (scope<>'global' AND target_id IS NOT NULL)),
  CONSTRAINT ck_platform_feature_flag_reason CHECK (length(btrim(reason)) >= 8)
);

-- statement-breakpoint

CREATE UNIQUE INDEX uq_platform_feature_flag_scope ON platform_feature_flags(flag_key, scope, COALESCE(target_id, ''));

-- statement-breakpoint

CREATE INDEX ix_platform_feature_flags_lookup ON platform_feature_flags(flag_key, scope, target_id);

-- statement-breakpoint

CREATE INDEX ix_platform_feature_flags_expiry ON platform_feature_flags(expires_at) WHERE expires_at IS NOT NULL;

-- statement-breakpoint

CREATE TABLE platform_break_glass_grants (
  id UUID PRIMARY KEY,
  actor_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  scope VARCHAR(120) NOT NULL,
  target_type VARCHAR(80) NOT NULL,
  target_id VARCHAR(255) NOT NULL,
  reason TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_platform_break_glass_expiry CHECK (expires_at > created_at),
  CONSTRAINT ck_platform_break_glass_reason CHECK (length(btrim(reason)) >= 8)
);

-- statement-breakpoint

CREATE INDEX ix_platform_break_glass_actor_expiry ON platform_break_glass_grants(actor_user_id, expires_at DESC);

-- statement-breakpoint

CREATE OR REPLACE FUNCTION platform_admin_reject_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'platform_admin_audit_events is append-only';
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_platform_admin_audit_immutable
BEFORE UPDATE OR DELETE ON platform_admin_audit_events
FOR EACH ROW EXECUTE FUNCTION platform_admin_reject_audit_mutation();

-- statement-breakpoint

CREATE OR REPLACE FUNCTION platform_admin_reject_break_glass_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'platform_break_glass_grants is append-only';
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_platform_break_glass_immutable
BEFORE UPDATE OR DELETE ON platform_break_glass_grants
FOR EACH ROW EXECUTE FUNCTION platform_admin_reject_break_glass_mutation();
