ALTER TABLE artifacts
    ADD COLUMN name VARCHAR(240) NOT NULL DEFAULT 'Untitled Artifact',
    ADD COLUMN rights_json JSONB NOT NULL DEFAULT '{"source_type":"legacy","owner_assertion":"unknown","license_type":"unknown"}'::jsonb,
    ADD COLUMN archived_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN retention_until TIMESTAMP WITH TIME ZONE,
    ADD COLUMN legal_hold BOOLEAN NOT NULL DEFAULT false;

-- statement-breakpoint

ALTER TABLE artifact_branches
    ADD COLUMN base_version_id UUID,
    ADD COLUMN created_by_type VARCHAR(32) NOT NULL DEFAULT 'system',
    ADD COLUMN created_by_id VARCHAR(200);

-- statement-breakpoint

ALTER TABLE artifact_branches
    ADD CONSTRAINT fk_artifact_branches_base_version_id_artifact_versions
    FOREIGN KEY(base_version_id) REFERENCES artifact_versions(id) ON DELETE SET NULL;

-- statement-breakpoint

UPDATE artifact_versions
SET content_hash = repeat('0', 64)
WHERE content_hash IS NULL;

-- statement-breakpoint

ALTER TABLE artifact_versions ALTER COLUMN content_hash SET NOT NULL;

-- statement-breakpoint

ALTER TABLE artifact_versions
    ADD CONSTRAINT ck_artifact_versions_content_hash
    CHECK (content_hash ~ '^[0-9a-f]{64}$');

-- statement-breakpoint

ALTER TABLE artifact_versions DROP CONSTRAINT ck_artifact_versions_status;

-- statement-breakpoint

ALTER TABLE artifact_versions
    ADD CONSTRAINT ck_artifact_versions_status
    CHECK (status IN ('draft','ready','approved','rejected','archived'));

-- statement-breakpoint

ALTER TABLE artifact_versions
    ADD COLUMN parent_version_id UUID,
    ADD COLUMN primary_file_id UUID,
    ADD COLUMN design_document_version_id UUID,
    ADD COLUMN constraint_snapshot_hash VARCHAR(64),
    ADD COLUMN rights_json JSONB NOT NULL DEFAULT '{"source_type":"legacy","owner_assertion":"unknown","license_type":"unknown"}'::jsonb,
    ADD COLUMN quality_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN provenance_status VARCHAR(32) NOT NULL DEFAULT 'PARTIAL',
    ADD COLUMN provenance_score NUMERIC(8, 5) NOT NULL DEFAULT 0;

-- statement-breakpoint

ALTER TABLE artifact_versions ALTER COLUMN created_by_id TYPE VARCHAR(200);

-- statement-breakpoint

ALTER TABLE artifact_versions
    ADD CONSTRAINT fk_artifact_versions_parent_version_id_artifact_versions
    FOREIGN KEY(parent_version_id) REFERENCES artifact_versions(id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_artifact_versions_design_document_version_id_design_document_versions
    FOREIGN KEY(design_document_version_id) REFERENCES design_document_versions(id) ON DELETE SET NULL,
    ADD CONSTRAINT ck_artifact_versions_not_self_parent CHECK (id <> parent_version_id),
    ADD CONSTRAINT ck_artifact_versions_provenance_status
    CHECK (provenance_status IN ('FULLY_TRACEABLE','PARTIAL')),
    ADD CONSTRAINT ck_artifact_versions_provenance_score_range
    CHECK (provenance_score >= 0 AND provenance_score <= 1),
    ADD CONSTRAINT ck_artifact_versions_constraint_snapshot_hash
    CHECK (constraint_snapshot_hash IS NULL OR constraint_snapshot_hash ~ '^[0-9a-f]{64}$');

-- statement-breakpoint

CREATE INDEX ix_artifact_versions_parent_version_id ON artifact_versions(parent_version_id);

-- statement-breakpoint

CREATE INDEX ix_artifact_versions_design_document_version_id
    ON artifact_versions(design_document_version_id);

-- statement-breakpoint

ALTER TABLE artifact_edges DROP CONSTRAINT ck_artifact_edges_edge_type;

-- statement-breakpoint

UPDATE artifact_edges
SET edge_type = 'GENERATED_FROM'
WHERE edge_type = 'GENERATED_FROM_ASSET';

-- statement-breakpoint

ALTER TABLE artifact_edges
    ADD CONSTRAINT ck_artifact_edges_edge_type
    CHECK (edge_type IN (
        'DERIVED_FROM','EDITED_FROM','GENERATED_FROM','COMPOSED_FROM',
        'RESIZED_FROM','EXPORTED_FROM','REFERENCE_USED'
    ));

-- statement-breakpoint

ALTER TABLE artifact_files DROP CONSTRAINT uq_artifact_files_bucket_key;

-- statement-breakpoint

ALTER TABLE artifact_files
    ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'original',
    ADD COLUMN width INTEGER,
    ADD COLUMN height INTEGER,
    ADD COLUMN duration_ms INTEGER,
    ADD COLUMN metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

-- statement-breakpoint

ALTER TABLE artifact_files
    ADD CONSTRAINT ck_artifact_files_role
    CHECK (role IN ('preview','original','thumbnail','web-optimized','print-pdf','layer-data')),
    ADD CONSTRAINT ck_artifact_files_dimensions
    CHECK ((width IS NULL OR width >= 1) AND (height IS NULL OR height >= 1)),
    ADD CONSTRAINT ck_artifact_files_duration_ms
    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    ADD CONSTRAINT ck_artifact_files_sha256_format
    CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT uq_artifact_files_version_bucket_key
    UNIQUE (artifact_version_id, bucket, object_key);

-- statement-breakpoint

CREATE INDEX ix_artifact_files_blob_checksum
    ON artifact_files(organization_id, checksum_sha256);

-- statement-breakpoint

ALTER TABLE artifact_versions
    ADD CONSTRAINT fk_artifact_versions_primary_file_id_artifact_files
    FOREIGN KEY(primary_file_id) REFERENCES artifact_files(id) ON DELETE SET NULL;
