CREATE TABLE task_dependencies (
	task_id UUID NOT NULL,
	depends_on_task_id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_task_dependencies PRIMARY KEY (task_id, depends_on_task_id),
	CONSTRAINT ck_task_dependencies_not_self_dependency CHECK (task_id <> depends_on_task_id),
	CONSTRAINT fk_task_dependencies_task_id_tasks FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE,
	CONSTRAINT fk_task_dependencies_depends_on_task_id_tasks FOREIGN KEY(depends_on_task_id) REFERENCES tasks (id) ON DELETE CASCADE,
	CONSTRAINT fk_task_dependencies_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_task_dependencies_depends_on ON task_dependencies (depends_on_task_id);

-- statement-breakpoint

CREATE INDEX ix_task_dependencies_organization_id ON task_dependencies (organization_id);

-- statement-breakpoint

CREATE TABLE generations (
	project_id UUID NOT NULL,
	operation_id UUID NOT NULL,
	agent_run_id UUID,
	provider VARCHAR(80) NOT NULL,
	model VARCHAR(160) NOT NULL,
	model_version VARCHAR(100),
	status VARCHAR(32) DEFAULT 'pending' NOT NULL,
	request_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	result_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	error_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_generations PRIMARY KEY (id),
	CONSTRAINT ck_generations_status CHECK (status IN ('pending','running','completed','failed','cancelled')),
	CONSTRAINT fk_generations_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
	CONSTRAINT fk_generations_operation_id_idempotency_operations FOREIGN KEY(operation_id) REFERENCES idempotency_operations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_generations_agent_run_id_agent_runs FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_generations_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_generations_organization_id ON generations (organization_id);

-- statement-breakpoint

CREATE TABLE artifact_branches (
	project_id UUID NOT NULL,
	artifact_id UUID,
	name VARCHAR(120) NOT NULL,
	head_version_id UUID,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	version INTEGER DEFAULT '1' NOT NULL,
	CONSTRAINT pk_artifact_branches PRIMARY KEY (id),
	CONSTRAINT uq_artifact_branch_name UNIQUE (project_id, artifact_id, name),
	CONSTRAINT fk_artifact_branches_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE,
	CONSTRAINT fk_artifact_branches_artifact_id_artifacts FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE CASCADE,
	CONSTRAINT fk_artifact_branches_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_artifact_branches_organization_id ON artifact_branches (organization_id);

-- statement-breakpoint

CREATE TABLE provider_requests (
	generation_id UUID,
	provider VARCHAR(80) NOT NULL,
	provider_request_id VARCHAR(255) NOT NULL,
	request_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	response_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	status VARCHAR(64) NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_provider_requests PRIMARY KEY (id),
	CONSTRAINT uq_provider_request_native_id UNIQUE (provider, provider_request_id),
	CONSTRAINT fk_provider_requests_generation_id_generations FOREIGN KEY(generation_id) REFERENCES generations (id) ON DELETE SET NULL,
	CONSTRAINT fk_provider_requests_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_provider_requests_organization_id ON provider_requests (organization_id);

-- statement-breakpoint

CREATE INDEX ix_provider_requests_native ON provider_requests (provider_request_id);

-- statement-breakpoint

CREATE TABLE artifact_versions (
	artifact_id UUID NOT NULL,
	branch_id UUID NOT NULL,
	version_number INTEGER NOT NULL,
	status VARCHAR(32) DEFAULT 'draft' NOT NULL,
	content_hash VARCHAR(64),
	metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	quality_score NUMERIC(8, 5),
	created_by_type VARCHAR(32) DEFAULT 'system' NOT NULL,
	created_by_id VARCHAR(160),
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_artifact_versions PRIMARY KEY (id),
	CONSTRAINT uq_artifact_version_number UNIQUE (artifact_id, branch_id, version_number),
	CONSTRAINT ck_artifact_versions_version_number_positive CHECK (version_number >= 1),
	CONSTRAINT ck_artifact_versions_status CHECK (status IN ('draft','ready','approved','rejected')),
	CONSTRAINT ck_artifact_versions_quality_score_range CHECK (quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)),
	CONSTRAINT fk_artifact_versions_artifact_id_artifacts FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE CASCADE,
	CONSTRAINT fk_artifact_versions_branch_id_artifact_branches FOREIGN KEY(branch_id) REFERENCES artifact_branches (id) ON DELETE RESTRICT,
	CONSTRAINT fk_artifact_versions_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_artifact_versions_artifact_version ON artifact_versions (artifact_id, version_number);

-- statement-breakpoint

CREATE INDEX ix_artifact_versions_organization_id ON artifact_versions (organization_id);

-- statement-breakpoint

CREATE TABLE cost_ledger (
	project_id UUID,
	task_id UUID,
	agent_run_id UUID,
	generation_id UUID,
	related_entry_id UUID,
	provider VARCHAR(80),
	model VARCHAR(160),
	entry_type VARCHAR(32) NOT NULL,
	amount NUMERIC(20, 8) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	quantity NUMERIC(30, 10),
	unit VARCHAR(80),
	provider_request_id UUID,
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_cost_ledger PRIMARY KEY (id),
	CONSTRAINT ck_cost_ledger_entry_type CHECK (entry_type IN ('charge','reversal','adjustment')),
	CONSTRAINT ck_cost_ledger_currency_format CHECK (currency ~ '^[A-Z]{3}$'),
	CONSTRAINT ck_cost_ledger_related_entry_semantics CHECK ((entry_type = 'charge' AND related_entry_id IS NULL) OR (entry_type IN ('reversal','adjustment') AND related_entry_id IS NOT NULL)),
	CONSTRAINT fk_cost_ledger_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE SET NULL,
	CONSTRAINT fk_cost_ledger_task_id_tasks FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE SET NULL,
	CONSTRAINT fk_cost_ledger_agent_run_id_agent_runs FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_cost_ledger_generation_id_generations FOREIGN KEY(generation_id) REFERENCES generations (id) ON DELETE SET NULL,
	CONSTRAINT fk_cost_ledger_related_entry_id_cost_ledger FOREIGN KEY(related_entry_id) REFERENCES cost_ledger (id) ON DELETE RESTRICT,
	CONSTRAINT fk_cost_ledger_provider_request_id_provider_requests FOREIGN KEY(provider_request_id) REFERENCES provider_requests (id) ON DELETE SET NULL,
	CONSTRAINT fk_cost_ledger_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_cost_ledger_organization_id ON cost_ledger (organization_id);

-- statement-breakpoint

CREATE INDEX ix_cost_ledger_org_occurred ON cost_ledger (organization_id, occurred_at);

-- statement-breakpoint

CREATE TABLE artifact_edges (
	from_artifact_version_id UUID NOT NULL,
	to_artifact_version_id UUID NOT NULL,
	edge_type VARCHAR(64) NOT NULL,
	metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_artifact_edges PRIMARY KEY (id),
	CONSTRAINT uq_artifact_edge UNIQUE (from_artifact_version_id, to_artifact_version_id, edge_type),
	CONSTRAINT ck_artifact_edges_not_self_edge CHECK (from_artifact_version_id <> to_artifact_version_id),
	CONSTRAINT ck_artifact_edges_edge_type CHECK (edge_type IN ('DERIVED_FROM','EDITED_FROM','COMPOSED_FROM','RESIZED_FROM','EXPORTED_FROM','GENERATED_FROM_ASSET')),
	CONSTRAINT fk_artifact_edges_from_artifact_version_id_artifact_versions FOREIGN KEY(from_artifact_version_id) REFERENCES artifact_versions (id) ON DELETE CASCADE,
	CONSTRAINT fk_artifact_edges_to_artifact_version_id_artifact_versions FOREIGN KEY(to_artifact_version_id) REFERENCES artifact_versions (id) ON DELETE CASCADE,
	CONSTRAINT fk_artifact_edges_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_artifact_edges_to ON artifact_edges (to_artifact_version_id);

-- statement-breakpoint

CREATE INDEX ix_artifact_edges_organization_id ON artifact_edges (organization_id);

-- statement-breakpoint

CREATE TABLE artifact_files (
	artifact_version_id UUID NOT NULL,
	bucket VARCHAR(128) NOT NULL,
	object_key TEXT NOT NULL,
	checksum_sha256 VARCHAR(64) NOT NULL,
	mime_type VARCHAR(255) NOT NULL,
	byte_size BIGINT NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_artifact_files PRIMARY KEY (id),
	CONSTRAINT uq_artifact_files_bucket_key UNIQUE (bucket, object_key),
	CONSTRAINT ck_artifact_files_byte_size_nonnegative CHECK (byte_size >= 0),
	CONSTRAINT fk_artifact_files_artifact_version_id_artifact_versions FOREIGN KEY(artifact_version_id) REFERENCES artifact_versions (id) ON DELETE CASCADE,
	CONSTRAINT fk_artifact_files_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_artifact_files_organization_id ON artifact_files (organization_id);

-- statement-breakpoint

CREATE TABLE artifact_provenance (
	artifact_version_id UUID NOT NULL,
	provenance_json JSONB NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	id UUID NOT NULL,
	organization_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_artifact_provenance PRIMARY KEY (id),
	CONSTRAINT fk_artifact_provenance_artifact_version_id_artifact_versions FOREIGN KEY(artifact_version_id) REFERENCES artifact_versions (id) ON DELETE CASCADE,
	CONSTRAINT fk_artifact_provenance_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_artifact_provenance_organization_id ON artifact_provenance (organization_id);

-- statement-breakpoint

ALTER TABLE design_documents ADD CONSTRAINT fk_design_documents_head_version_id_versions FOREIGN KEY(head_version_id) REFERENCES design_document_versions (id) ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE artifact_branches ADD CONSTRAINT fk_artifact_branches_head_version_id_versions FOREIGN KEY(head_version_id) REFERENCES artifact_versions (id) ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE brand_fonts ADD CONSTRAINT fk_brand_fonts_source_asset_id_assets FOREIGN KEY(source_asset_id) REFERENCES assets (id) ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE brand_logos ADD CONSTRAINT fk_brand_logos_asset_id_assets FOREIGN KEY(asset_id) REFERENCES assets (id) ON DELETE RESTRICT;

-- statement-breakpoint

ALTER TABLE projects ADD CONSTRAINT fk_projects_active_branch_id_artifact_branches FOREIGN KEY(active_branch_id) REFERENCES artifact_branches (id) ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE agent_runs ADD CONSTRAINT ck_agent_runs_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE approvals ADD CONSTRAINT ck_approvals_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE artifact_branches ADD CONSTRAINT ck_artifact_branches_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE artifacts ADD CONSTRAINT ck_artifacts_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE asset_metadata ADD CONSTRAINT ck_asset_metadata_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE asset_rights ADD CONSTRAINT ck_asset_rights_version_positive CHECK (version >= 1);
