ALTER TABLE design_documents DROP CONSTRAINT fk_design_documents_head_version_id_versions;

-- statement-breakpoint

ALTER TABLE artifact_branches DROP CONSTRAINT fk_artifact_branches_head_version_id_versions;

-- statement-breakpoint

ALTER TABLE brand_fonts DROP CONSTRAINT fk_brand_fonts_source_asset_id_assets;

-- statement-breakpoint

ALTER TABLE brand_logos DROP CONSTRAINT fk_brand_logos_asset_id_assets;

-- statement-breakpoint

ALTER TABLE projects DROP CONSTRAINT fk_projects_active_branch_id_artifact_branches;

-- statement-breakpoint

DROP TABLE artifact_provenance;

-- statement-breakpoint

DROP TABLE artifact_files;

-- statement-breakpoint

DROP TABLE artifact_edges;

-- statement-breakpoint

DROP TABLE cost_ledger;

-- statement-breakpoint

DROP TABLE artifact_versions;

-- statement-breakpoint

DROP TABLE provider_requests;

-- statement-breakpoint

DROP TABLE artifact_branches;

-- statement-breakpoint

DROP TABLE generations;

-- statement-breakpoint

DROP TABLE task_dependencies;

-- statement-breakpoint

DROP TABLE agent_run_steps;

-- statement-breakpoint

DROP TABLE artifacts;

-- statement-breakpoint

DROP TABLE design_document_versions;

-- statement-breakpoint

DROP TABLE asset_rights;

-- statement-breakpoint

DROP TABLE asset_embeddings;

-- statement-breakpoint

DROP TABLE asset_metadata;

-- statement-breakpoint

DROP TABLE asset_previews;

-- statement-breakpoint

DROP TABLE asset_files;

-- statement-breakpoint

DROP TABLE approvals;

-- statement-breakpoint

DROP TABLE tasks;

-- statement-breakpoint

DROP TABLE agent_runs;

-- statement-breakpoint

DROP TABLE design_documents;
