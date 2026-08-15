CREATE INDEX ix_projects_organization_id ON projects (organization_id);

-- statement-breakpoint

CREATE INDEX ix_projects_org_created ON projects (organization_id, created_at);

-- statement-breakpoint

CREATE TABLE project_members (
	project_id UUID NOT NULL,
	user_id UUID NOT NULL,
	role VARCHAR(32) NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_project_members PRIMARY KEY (id),
	CONSTRAINT uq_project_members_project_user UNIQUE (project_id, user_id),
	CONSTRAINT ck_project_members_role CHECK (role IN ('admin','editor','viewer')),
	CONSTRAINT fk_project_members_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
	CONSTRAINT fk_project_members_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	CONSTRAINT fk_project_members_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_project_members_organization_id ON project_members (organization_id);

-- statement-breakpoint

CREATE TABLE assets (
	project_id UUID,
	source VARCHAR(64) NOT NULL,
	mime_type VARCHAR(255) NOT NULL,
	status VARCHAR(32) DEFAULT 'pending' NOT NULL,
	semantic_metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_assets PRIMARY KEY (id),
	CONSTRAINT ck_assets_status CHECK (status IN ('pending','ready','failed','deleted')),
	CONSTRAINT fk_assets_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE SET NULL,
	CONSTRAINT fk_assets_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_assets_org_created ON assets (organization_id, created_at);

-- statement-breakpoint

CREATE INDEX ix_assets_organization_id ON assets (organization_id);

-- statement-breakpoint

CREATE TABLE design_documents (
	project_id UUID NOT NULL,
	name VARCHAR(240) NOT NULL,
	ir_version VARCHAR(32) NOT NULL,
	head_version_id UUID,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_design_documents PRIMARY KEY (id),
	CONSTRAINT fk_design_documents_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
	CONSTRAINT fk_design_documents_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_design_documents_organization_id ON design_documents (organization_id);

-- statement-breakpoint

CREATE TABLE agent_runs (
	project_id UUID NOT NULL,
	thread_id VARCHAR(200) NOT NULL,
	graph_version VARCHAR(80) NOT NULL,
	agent_config_version VARCHAR(80) NOT NULL,
	status VARCHAR(32) DEFAULT 'pending' NOT NULL,
	budget_amount NUMERIC(20, 8) NOT NULL,
	budget_currency VARCHAR(3) NOT NULL,
	usage_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	trace_refs_json JSONB DEFAULT '[]'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_agent_runs PRIMARY KEY (id),
	CONSTRAINT ck_agent_runs_status CHECK (status IN ('pending','running','waiting_user','cancel_requested','cancelled','paused','succeeded','failed')),
	CONSTRAINT ck_agent_runs_budget_nonnegative CHECK (budget_amount >= 0),
	CONSTRAINT ck_agent_runs_budget_currency_format CHECK (budget_currency ~ '^[A-Z]{3}$'),
	CONSTRAINT fk_agent_runs_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
	CONSTRAINT fk_agent_runs_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_agent_runs_organization_id ON agent_runs (organization_id);

-- statement-breakpoint

CREATE INDEX ix_agent_runs_project_created ON agent_runs (project_id, created_at);

-- statement-breakpoint

CREATE TABLE tasks (
	project_id UUID NOT NULL,
	parent_task_id UUID,
	task_type VARCHAR(100) NOT NULL,
	name VARCHAR(240) NOT NULL,
	status VARCHAR(32) DEFAULT 'pending' NOT NULL,
	owner_agent_key VARCHAR(160),
	input_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	output_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	priority INTEGER DEFAULT '0' NOT NULL,
	attempt_count INTEGER DEFAULT '0' NOT NULL,
	max_attempts INTEGER DEFAULT '3' NOT NULL,
	budget_reserved NUMERIC(20, 8) DEFAULT '0' NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_tasks PRIMARY KEY (id),
	CONSTRAINT ck_tasks_status CHECK (status IN ('pending','ready','running','waiting_user','waiting_dependency','succeeded','failed','cancelled')),
	CONSTRAINT ck_tasks_attempts CHECK (attempt_count >= 0 AND max_attempts >= 1),
	CONSTRAINT ck_tasks_budget_reserved_nonnegative CHECK (budget_reserved >= 0),
	CONSTRAINT ck_tasks_not_self_parent CHECK (id <> parent_task_id),
	CONSTRAINT fk_tasks_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
	CONSTRAINT fk_tasks_parent_task_id_tasks FOREIGN KEY(parent_task_id) REFERENCES tasks (id) ON DELETE SET NULL,
	CONSTRAINT fk_tasks_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_tasks_organization_id ON tasks (organization_id);

-- statement-breakpoint

CREATE INDEX ix_tasks_project_status ON tasks (project_id, status);

-- statement-breakpoint

CREATE INDEX ix_tasks_project_created ON tasks (project_id, created_at);

-- statement-breakpoint

CREATE TABLE approvals (
	project_id UUID NOT NULL,
	subject_type VARCHAR(64) NOT NULL,
	subject_id UUID NOT NULL,
	status VARCHAR(32) DEFAULT 'pending' NOT NULL,
	requested_by UUID,
	decided_by UUID,
	reason TEXT,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_approvals PRIMARY KEY (id),
	CONSTRAINT ck_approvals_status CHECK (status IN ('pending','approved','rejected','cancelled')),
	CONSTRAINT fk_approvals_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
	CONSTRAINT fk_approvals_requested_by_users FOREIGN KEY(requested_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_approvals_decided_by_users FOREIGN KEY(decided_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_approvals_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_approvals_organization_id ON approvals (organization_id);

-- statement-breakpoint

CREATE TABLE asset_files (
	asset_id UUID NOT NULL,
	bucket VARCHAR(128) NOT NULL,
	object_key TEXT NOT NULL,
	checksum_sha256 VARCHAR(64) NOT NULL,
	byte_size BIGINT NOT NULL,
	width INTEGER,
	height INTEGER,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_asset_files PRIMARY KEY (id),
	CONSTRAINT uq_asset_files_bucket_key UNIQUE (bucket, object_key),
	CONSTRAINT ck_asset_files_byte_size_nonnegative CHECK (byte_size >= 0),
	CONSTRAINT ck_asset_files_sha256_format CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT fk_asset_files_asset_id_assets FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE CASCADE,
	CONSTRAINT fk_asset_files_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_asset_files_organization_id ON asset_files (organization_id);

-- statement-breakpoint

CREATE TABLE asset_previews (
	asset_id UUID NOT NULL,
	kind VARCHAR(64) NOT NULL,
	bucket VARCHAR(128) NOT NULL,
	object_key TEXT NOT NULL,
	checksum_sha256 VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_asset_previews PRIMARY KEY (id),
	CONSTRAINT fk_asset_previews_asset_id_assets FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE CASCADE,
	CONSTRAINT fk_asset_previews_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_asset_previews_organization_id ON asset_previews (organization_id);

-- statement-breakpoint

CREATE TABLE asset_metadata (
	asset_id UUID NOT NULL,
	namespace VARCHAR(80) NOT NULL,
	metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_asset_metadata PRIMARY KEY (id),
	CONSTRAINT uq_asset_metadata_asset_namespace UNIQUE (asset_id, namespace),
	CONSTRAINT fk_asset_metadata_asset_id_assets FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE CASCADE,
	CONSTRAINT fk_asset_metadata_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_asset_metadata_organization_id ON asset_metadata (organization_id);

-- statement-breakpoint

CREATE TABLE asset_embeddings (
	asset_id UUID NOT NULL,
	embedding_model VARCHAR(160) NOT NULL,
	embedding_version VARCHAR(80) NOT NULL,
	dimensions INTEGER NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	embedding vector NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_asset_embeddings PRIMARY KEY (id),
	CONSTRAINT uq_asset_embedding_version UNIQUE (asset_id, embedding_model, embedding_version, content_hash),
	CONSTRAINT ck_asset_embeddings_dimensions_positive CHECK (dimensions > 0),
	CONSTRAINT fk_asset_embeddings_asset_id_assets FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE CASCADE,
	CONSTRAINT fk_asset_embeddings_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_asset_embeddings_organization_id ON asset_embeddings (organization_id);

-- statement-breakpoint

CREATE TABLE asset_rights (
	asset_id UUID NOT NULL,
	rights_level VARCHAR(32) NOT NULL,
	commercial_use BOOLEAN DEFAULT 'false' NOT NULL,
	attribution_required BOOLEAN DEFAULT 'false' NOT NULL,
	source_uri TEXT,
	notes TEXT,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_asset_rights PRIMARY KEY (id),
	CONSTRAINT ck_asset_rights_rights_level CHECK (rights_level IN ('unknown','owned','licensed','public_domain','restricted')),
	CONSTRAINT uq_asset_rights_asset_id UNIQUE (asset_id),
	CONSTRAINT fk_asset_rights_asset_id_assets FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE CASCADE,
	CONSTRAINT fk_asset_rights_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_asset_rights_organization_id ON asset_rights (organization_id);

-- statement-breakpoint

CREATE TABLE design_document_versions (
	design_document_id UUID NOT NULL,
	version_number INTEGER NOT NULL,
	parent_version_id UUID,
	content_json JSONB NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	created_by UUID,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_design_document_versions PRIMARY KEY (id),
	CONSTRAINT uq_design_document_version_number UNIQUE (design_document_id, version_number),
	CONSTRAINT ck_design_document_versions_version_number_positive CHECK (version_number >= 1),
	CONSTRAINT ck_design_document_versions_not_self_parent CHECK (id <> parent_version_id),
	CONSTRAINT fk_design_document_versions_design_document_id_design_documents FOREIGN KEY(design_document_id) REFERENCES design_documents (id) ON DELETE CASCADE,
	CONSTRAINT fk_design_document_versions_parent_version_id_design_do_dfa8 FOREIGN KEY(parent_version_id) REFERENCES design_document_versions (id) ON DELETE RESTRICT,
	CONSTRAINT fk_design_document_versions_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL,
	CONSTRAINT fk_design_document_versions_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_design_document_versions_organization_id ON design_document_versions (organization_id);

-- statement-breakpoint

CREATE TABLE artifacts (
	project_id UUID NOT NULL,
	kind VARCHAR(80) NOT NULL,
	design_document_id UUID,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_artifacts PRIMARY KEY (id),
	CONSTRAINT fk_artifacts_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
	CONSTRAINT fk_artifacts_design_document_id_design_documents FOREIGN KEY(design_document_id) REFERENCES design_documents (id) ON DELETE SET NULL,
	CONSTRAINT fk_artifacts_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_artifacts_organization_id ON artifacts (organization_id);

-- statement-breakpoint

CREATE TABLE agent_run_steps (
	agent_run_id UUID NOT NULL,
	step_key VARCHAR(160) NOT NULL,
	status VARCHAR(32) NOT NULL,
	input_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	output_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_agent_run_steps PRIMARY KEY (id),
	CONSTRAINT uq_agent_run_step_key UNIQUE (agent_run_id, step_key),
	CONSTRAINT fk_agent_run_steps_agent_run_id_agent_runs FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id) ON DELETE CASCADE,
	CONSTRAINT fk_agent_run_steps_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_agent_run_steps_organization_id ON agent_run_steps (organization_id);
