DROP TABLE IF EXISTS auth_security_events;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_api_tokens ON api_tokens;

-- statement-breakpoint

DROP TABLE IF EXISTS api_tokens;

-- statement-breakpoint

DROP TABLE IF EXISTS auth_one_time_tokens;

-- statement-breakpoint

DROP TABLE IF EXISTS auth_sessions;

-- statement-breakpoint

DROP TABLE IF EXISTS password_credentials;

-- statement-breakpoint

ALTER TABLE organization_members
DROP CONSTRAINT ck_organization_members_role;

-- statement-breakpoint

ALTER TABLE organization_members
ADD CONSTRAINT ck_organization_members_role
CHECK (role IN ('owner','admin','member','viewer'));

-- statement-breakpoint

ALTER TABLE users
DROP COLUMN IF EXISTS email_verified_at;
