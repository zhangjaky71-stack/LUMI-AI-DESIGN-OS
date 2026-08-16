ALTER TABLE users
ADD COLUMN email_verified_at TIMESTAMP WITH TIME ZONE;

-- statement-breakpoint

ALTER TABLE organization_members
DROP CONSTRAINT ck_organization_members_role;

-- statement-breakpoint

ALTER TABLE organization_members
ADD CONSTRAINT ck_organization_members_role
CHECK (role IN ('owner','admin','editor','viewer','billing'));

-- statement-breakpoint

CREATE TABLE password_credentials (
    user_id UUID NOT NULL,
    password_hash TEXT NOT NULL,
    algorithm VARCHAR(32) DEFAULT 'argon2id' NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_password_credentials PRIMARY KEY (user_id),
    CONSTRAINT ck_password_credentials_algorithm_argon2id CHECK (algorithm = 'argon2id'),
    CONSTRAINT ck_password_credentials_encoded_hash_argon2id CHECK (password_hash LIKE '$argon2id$%'),
    CONSTRAINT fk_password_credentials_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- statement-breakpoint

CREATE TABLE auth_sessions (
    session_hash VARCHAR(64) NOT NULL,
    user_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
    recent_auth_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    user_agent_hash VARCHAR(64),
    ip_risk_metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT pk_auth_sessions PRIMARY KEY (session_hash),
    CONSTRAINT ck_auth_sessions_session_hash_sha256 CHECK (session_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_auth_sessions_expires_after_created CHECK (expires_at > created_at),
    CONSTRAINT fk_auth_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- statement-breakpoint

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

-- statement-breakpoint

CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions (expires_at);

-- statement-breakpoint

CREATE TABLE auth_one_time_tokens (
    purpose VARCHAR(32) NOT NULL,
    token_hash VARCHAR(64) NOT NULL,
    user_id UUID,
    email VARCHAR(320),
    organization_id UUID,
    role VARCHAR(32),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_auth_one_time_tokens PRIMARY KEY (id),
    CONSTRAINT uq_auth_one_time_tokens_token_hash UNIQUE (token_hash),
    CONSTRAINT ck_auth_one_time_tokens_purpose CHECK (purpose IN ('invite','password_reset','email_verification')),
    CONSTRAINT ck_auth_one_time_tokens_token_hash_sha256 CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_auth_one_time_tokens_expires_after_created CHECK (expires_at > created_at),
    CONSTRAINT ck_auth_one_time_tokens_invite_payload CHECK ((purpose <> 'invite') OR (email IS NOT NULL AND organization_id IS NOT NULL AND role IS NOT NULL)),
    CONSTRAINT ck_auth_one_time_tokens_password_reset_user CHECK ((purpose <> 'password_reset') OR user_id IS NOT NULL),
    CONSTRAINT fk_auth_one_time_tokens_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_auth_one_time_tokens_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE
);

-- statement-breakpoint

CREATE INDEX ix_auth_one_time_tokens_user_id ON auth_one_time_tokens (user_id);

-- statement-breakpoint

CREATE INDEX ix_auth_one_time_tokens_organization_id ON auth_one_time_tokens (organization_id);

-- statement-breakpoint

CREATE INDEX ix_auth_one_time_tokens_expires_at ON auth_one_time_tokens (expires_at);

-- statement-breakpoint

CREATE TABLE api_tokens (
    name VARCHAR(120) NOT NULL,
    prefix VARCHAR(32) NOT NULL,
    secret_hash VARCHAR(64) NOT NULL,
    scopes_json JSONB NOT NULL,
    created_by_user_id UUID NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    last_used_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_api_tokens PRIMARY KEY (id),
    CONSTRAINT uq_api_tokens_secret_hash UNIQUE (secret_hash),
    CONSTRAINT uq_api_token_org_prefix UNIQUE (organization_id, prefix),
    CONSTRAINT ck_api_tokens_secret_hash_sha256 CHECK (secret_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_api_tokens_created_by_user_id_users FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT fk_api_tokens_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_api_tokens_organization_id ON api_tokens (organization_id);

-- statement-breakpoint

CREATE INDEX ix_api_tokens_expires_at ON api_tokens (expires_at);

-- statement-breakpoint

ALTER TABLE api_tokens ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_api_tokens ON api_tokens
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

CREATE TABLE auth_security_events (
    category VARCHAR(80) NOT NULL,
    organization_id UUID,
    actor_id VARCHAR(200),
    subject_user_id UUID,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
    id UUID NOT NULL,
    CONSTRAINT pk_auth_security_events PRIMARY KEY (id),
    CONSTRAINT fk_auth_security_events_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE SET NULL,
    CONSTRAINT fk_auth_security_events_subject_user_id_users FOREIGN KEY(subject_user_id) REFERENCES users (id) ON DELETE SET NULL
);

-- statement-breakpoint

CREATE INDEX ix_auth_security_events_occurred_at ON auth_security_events (occurred_at);

-- statement-breakpoint

CREATE INDEX ix_auth_security_events_organization_id ON auth_security_events (organization_id);

-- statement-breakpoint

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
      password_credentials, auth_sessions, auth_one_time_tokens, api_tokens
      TO lumi_app;
    GRANT SELECT, INSERT ON TABLE auth_security_events TO lumi_app;
    REVOKE UPDATE, DELETE ON TABLE auth_security_events FROM lumi_app;
  END IF;
END;
$$;
