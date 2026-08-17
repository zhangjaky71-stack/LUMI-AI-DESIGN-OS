DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM artifact_versions WHERE status = 'archived') THEN
        RAISE EXCEPTION 'cannot downgrade NODE-42: archived artifact versions exist';
    END IF;
    IF EXISTS (SELECT 1 FROM artifact_edges WHERE edge_type = 'REFERENCE_USED') THEN
        RAISE EXCEPTION 'cannot downgrade NODE-42: REFERENCE_USED lineage exists';
    END IF;
    IF EXISTS (
        SELECT 1 FROM artifact_files
        GROUP BY bucket, object_key
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'cannot downgrade NODE-42: storage blobs are referenced by multiple artifact files';
    END IF;
END $$;

-- statement-breakpoint

ALTER TABLE artifact_versions
    DROP CONSTRAINT fk_artifact_versions_primary_file_id_artifact_files;

-- statement-breakpoint

DROP INDEX ix_artifact_files_blob_checksum;

-- statement-breakpoint

ALTER TABLE artifact_files DROP CONSTRAINT uq_artifact_files_version_bucket_key;

-- statement-breakpoint

ALTER TABLE artifact_files
    DROP CONSTRAINT ck_artifact_files_sha256_format,
    DROP CONSTRAINT ck_artifact_files_duration_ms,
    DROP CONSTRAINT ck_artifact_files_dimensions,
    DROP CONSTRAINT ck_artifact_files_role;

-- statement-breakpoint

ALTER TABLE artifact_files
    DROP COLUMN metadata_json,
    DROP COLUMN duration_ms,
    DROP COLUMN height,
    DROP COLUMN width,
    DROP COLUMN role;

-- statement-breakpoint

ALTER TABLE artifact_files
    ADD CONSTRAINT uq_artifact_files_bucket_key UNIQUE(bucket, object_key);

-- statement-breakpoint

ALTER TABLE artifact_edges DROP CONSTRAINT ck_artifact_edges_edge_type;

-- statement-breakpoint

UPDATE artifact_edges SET edge_type = 'GENERATED_FROM_ASSET' WHERE edge_type = 'GENERATED_FROM';

-- statement-breakpoint

ALTER TABLE artifact_edges
    ADD CONSTRAINT ck_artifact_edges_edge_type
    CHECK (edge_type IN (
        'DERIVED_FROM','EDITED_FROM','COMPOSED_FROM','RESIZED_FROM',
        'EXPORTED_FROM','GENERATED_FROM_ASSET'
    ));

-- statement-breakpoint

DROP INDEX ix_artifact_versions_design_document_version_id;

-- statement-breakpoint

DROP INDEX ix_artifact_versions_parent_version_id;

-- statement-breakpoint

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM artifact_versions WHERE length(created_by_id) > 160) THEN
        RAISE EXCEPTION 'cannot downgrade NODE-42: artifact version creator id exceeds 160 chars';
    END IF;
END $$;

-- statement-breakpoint

ALTER TABLE artifact_versions ALTER COLUMN created_by_id TYPE VARCHAR(160);

-- statement-breakpoint

ALTER TABLE artifact_versions
    DROP CONSTRAINT ck_artifact_versions_constraint_snapshot_hash,
    DROP CONSTRAINT ck_artifact_versions_provenance_score_range,
    DROP CONSTRAINT ck_artifact_versions_provenance_status,
    DROP CONSTRAINT ck_artifact_versions_not_self_parent,
    DROP CONSTRAINT fk_artifact_versions_design_document_version_id_design_document_versions,
    DROP CONSTRAINT fk_artifact_versions_parent_version_id_artifact_versions;

-- statement-breakpoint

ALTER TABLE artifact_versions
    DROP COLUMN provenance_score,
    DROP COLUMN provenance_status,
    DROP COLUMN quality_summary_json,
    DROP COLUMN rights_json,
    DROP COLUMN constraint_snapshot_hash,
    DROP COLUMN design_document_version_id,
    DROP COLUMN primary_file_id,
    DROP COLUMN parent_version_id;

-- statement-breakpoint

ALTER TABLE artifact_versions DROP CONSTRAINT ck_artifact_versions_content_hash;

-- statement-breakpoint

ALTER TABLE artifact_versions ALTER COLUMN content_hash DROP NOT NULL;

-- statement-breakpoint

ALTER TABLE artifact_versions DROP CONSTRAINT ck_artifact_versions_status;

-- statement-breakpoint

ALTER TABLE artifact_versions
    ADD CONSTRAINT ck_artifact_versions_status
    CHECK (status IN ('draft','ready','approved','rejected'));

-- statement-breakpoint

ALTER TABLE artifact_branches
    DROP CONSTRAINT fk_artifact_branches_base_version_id_artifact_versions;

-- statement-breakpoint

ALTER TABLE artifact_branches
    DROP COLUMN created_by_id,
    DROP COLUMN created_by_type,
    DROP COLUMN base_version_id;

-- statement-breakpoint

ALTER TABLE artifacts
    DROP COLUMN legal_hold,
    DROP COLUMN retention_until,
    DROP COLUMN archived_at,
    DROP COLUMN rights_json,
    DROP COLUMN name;
