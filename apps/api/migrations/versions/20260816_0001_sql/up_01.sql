CREATE EXTENSION IF NOT EXISTS vector;

-- statement-breakpoint

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- statement-breakpoint

CREATE TABLE users (
	email VARCHAR(320) NOT NULL,
	display_name VARCHAR(200) NOT NULL,
	status VARCHAR(32) DEFAULT 'active' NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_users PRIMARY KEY (id),
	CONSTRAINT ck_users_status CHECK (status IN ('active','disabled')),
	CONSTRAINT uq_users_email UNIQUE (email)
);

-- statement-breakpoint

CREATE TABLE organizations (
	name VARCHAR(200) NOT NULL,
	slug VARCHAR(120) NOT NULL,
	status VARCHAR(32) DEFAULT 'active' NOT NULL,
	plan VARCHAR(64) DEFAULT 'free' NOT NULL,
	settings_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_organizations PRIMARY KEY (id),
	CONSTRAINT ck_organizations_status CHECK (status IN ('active','suspended','closed')),
	CONSTRAINT uq_organizations_slug UNIQUE (slug)
);

-- statement-breakpoint

CREATE TABLE organization_members (
	user_id UUID NOT NULL,
	role VARCHAR(32) NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_organization_members PRIMARY KEY (id),
	CONSTRAINT uq_organization_members_org_user UNIQUE (organization_id, user_id),
	CONSTRAINT ck_organization_members_role CHECK (role IN ('owner','admin','member','viewer')),
	CONSTRAINT fk_organization_members_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	CONSTRAINT fk_organization_members_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_organization_members_organization_id ON organization_members (organization_id);

-- statement-breakpoint

CREATE TABLE workspaces (
	name VARCHAR(200) NOT NULL,
	settings_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_workspaces PRIMARY KEY (id),
	CONSTRAINT fk_workspaces_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_workspaces_organization_id ON workspaces (organization_id);

-- statement-breakpoint

CREATE TABLE auth_identities (
	user_id UUID NOT NULL,
	provider VARCHAR(64) NOT NULL,
	provider_subject VARCHAR(255) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_auth_identities PRIMARY KEY (id),
	CONSTRAINT uq_auth_identity_provider_subject UNIQUE (provider, provider_subject),
	CONSTRAINT fk_auth_identities_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- statement-breakpoint

CREATE TABLE brands (
	name VARCHAR(200) NOT NULL,
	profile_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_brands PRIMARY KEY (id),
	CONSTRAINT fk_brands_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_brands_organization_id ON brands (organization_id);

-- statement-breakpoint

CREATE TABLE idempotency_operations (
	idempotency_key VARCHAR(255) NOT NULL,
	operation_type VARCHAR(100) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	status VARCHAR(32) DEFAULT 'started' NOT NULL,
	response_json JSONB,
	expires_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_idempotency_operations PRIMARY KEY (id),
	CONSTRAINT uq_idempotency_org_key UNIQUE (organization_id, idempotency_key),
	CONSTRAINT ck_idempotency_operations_status CHECK (status IN ('started','completed','failed')),
	CONSTRAINT fk_idempotency_operations_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_idempotency_operations_organization_id ON idempotency_operations (organization_id);

-- statement-breakpoint

CREATE TABLE usage_counters (
	period_key VARCHAR(40) NOT NULL,
	metric_key VARCHAR(100) NOT NULL,
	quantity NUMERIC(30, 10) DEFAULT '0' NOT NULL,
	unit VARCHAR(80) NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_usage_counters PRIMARY KEY (id),
	CONSTRAINT uq_usage_counter_scope UNIQUE (organization_id, period_key, metric_key),
	CONSTRAINT fk_usage_counters_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_usage_counters_organization_id ON usage_counters (organization_id);

-- statement-breakpoint

CREATE TABLE outbox_events (
	event_type VARCHAR(160) NOT NULL,
	aggregate_type VARCHAR(100) NOT NULL,
	aggregate_id UUID NOT NULL,
	payload_json JSONB NOT NULL,
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	published_at TIMESTAMP WITH TIME ZONE,
	publish_attempts INTEGER DEFAULT '0' NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_outbox_events PRIMARY KEY (id),
	CONSTRAINT fk_outbox_events_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_outbox_unpublished_created ON outbox_events (published_at, created_at);

-- statement-breakpoint

CREATE INDEX ix_outbox_events_organization_id ON outbox_events (organization_id);

-- statement-breakpoint

CREATE TABLE inbox_events (
	event_id UUID NOT NULL,
	consumer VARCHAR(160) NOT NULL,
	processed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_inbox_events PRIMARY KEY (event_id, consumer),
	CONSTRAINT fk_inbox_events_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_inbox_events_organization_id ON inbox_events (organization_id);

-- statement-breakpoint

CREATE TABLE audit_events (
	actor_type VARCHAR(64) NOT NULL,
	actor_id VARCHAR(160),
	action VARCHAR(160) NOT NULL,
	subject_type VARCHAR(100) NOT NULL,
	subject_id VARCHAR(160) NOT NULL,
	details_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	previous_hash VARCHAR(64),
	event_hash VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_audit_events PRIMARY KEY (id),
	CONSTRAINT fk_audit_events_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_audit_events_organization_id ON audit_events (organization_id);

-- statement-breakpoint

CREATE TABLE workspace_members (
	workspace_id UUID NOT NULL,
	user_id UUID NOT NULL,
	role VARCHAR(32) NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_workspace_members PRIMARY KEY (id),
	CONSTRAINT uq_workspace_members_workspace_user UNIQUE (workspace_id, user_id),
	CONSTRAINT ck_workspace_members_role CHECK (role IN ('admin','editor','viewer')),
	CONSTRAINT fk_workspace_members_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
	CONSTRAINT fk_workspace_members_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	CONSTRAINT fk_workspace_members_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_workspace_members_organization_id ON workspace_members (organization_id);

-- statement-breakpoint

CREATE TABLE brand_palettes (
	brand_id UUID NOT NULL,
	name VARCHAR(120) NOT NULL,
	colors_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_brand_palettes PRIMARY KEY (id),
	CONSTRAINT fk_brand_palettes_brand_id_brands FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE CASCADE,
	CONSTRAINT fk_brand_palettes_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_brand_palettes_organization_id ON brand_palettes (organization_id);

-- statement-breakpoint

CREATE TABLE brand_fonts (
	brand_id UUID NOT NULL,
	family VARCHAR(200) NOT NULL,
	source_asset_id UUID,
	usage_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_brand_fonts PRIMARY KEY (id),
	CONSTRAINT fk_brand_fonts_brand_id_brands FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE CASCADE,
	CONSTRAINT fk_brand_fonts_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_brand_fonts_organization_id ON brand_fonts (organization_id);

-- statement-breakpoint

CREATE TABLE brand_logos (
	brand_id UUID NOT NULL,
	asset_id UUID NOT NULL,
	variant VARCHAR(80) DEFAULT 'primary' NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_brand_logos PRIMARY KEY (id),
	CONSTRAINT fk_brand_logos_brand_id_brands FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE CASCADE,
	CONSTRAINT fk_brand_logos_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_brand_logos_organization_id ON brand_logos (organization_id);

-- statement-breakpoint

CREATE TABLE brand_rules (
	brand_id UUID NOT NULL,
	rule_type VARCHAR(80) NOT NULL,
	severity VARCHAR(32) NOT NULL,
	rule_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_brand_rules PRIMARY KEY (id),
	CONSTRAINT ck_brand_rules_severity CHECK (severity IN ('hard','soft','advisory')),
	CONSTRAINT fk_brand_rules_brand_id_brands FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE CASCADE,
	CONSTRAINT fk_brand_rules_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_brand_rules_organization_id ON brand_rules (organization_id);

-- statement-breakpoint

CREATE TABLE projects (
	workspace_id UUID NOT NULL,
	name VARCHAR(240) NOT NULL,
	status VARCHAR(32) DEFAULT 'draft' NOT NULL,
	brief_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	brand_id UUID,
	active_branch_id UUID,
	settings_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	created_by UUID,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_projects PRIMARY KEY (id),
	CONSTRAINT ck_projects_status CHECK (status IN ('draft','active','paused','archived')),
	CONSTRAINT fk_projects_workspace_id_workspaces FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	CONSTRAINT fk_projects_brand_id_brands FOREIGN KEY(brand_id) REFERENCES brands (id) ON DELETE SET NULL,
	CONSTRAINT fk_projects_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_projects_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_projects_org_status ON projects (organization_id, status);
