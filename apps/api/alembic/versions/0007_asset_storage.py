"""Add Asset Storage upload sessions, validation runs and explicit rights metadata.

Revision ID: 0007_asset_storage
Revises: 0006_project_core
Create Date: 2026-08-13
"""

from collections.abc import Iterable

from alembic import op

revision = "0007_asset_storage"
down_revision = "0006_project_core"
branch_labels = None
depends_on = None


def _execute(statements: Iterable[str]) -> None:
    for statement in statements:
        op.execute(statement)


UPGRADE_STATEMENTS = (
    "ALTER TABLE assets ADD COLUMN status varchar(32) NOT NULL DEFAULT 'ready'",
    "ALTER TABLE assets ADD COLUMN rejection_code varchar(100)",
    "ALTER TABLE assets ADD CONSTRAINT ck_assets_status CHECK (status IN ('uploading','scanning','ready','rejected'))",
    "ALTER TABLE assets ALTER COLUMN status SET DEFAULT 'uploading'",
    "ALTER TABLE asset_rights ADD COLUMN source_type varchar(32) NOT NULL DEFAULT 'UNKNOWN'",
    "ALTER TABLE asset_rights ADD COLUMN owner_assertion text",
    "ALTER TABLE asset_rights ADD COLUMN license_type varchar(64) NOT NULL DEFAULT 'UNKNOWN'",
    "ALTER TABLE asset_rights ADD COLUMN commercial_use varchar(16) NOT NULL DEFAULT 'UNKNOWN'",
    "ALTER TABLE asset_rights ADD COLUMN redistribution varchar(16) NOT NULL DEFAULT 'UNKNOWN'",
    "ALTER TABLE asset_rights ADD COLUMN training_use varchar(16) NOT NULL DEFAULT 'UNKNOWN'",
    "ALTER TABLE asset_rights ADD COLUMN source_reference text",
    "ALTER TABLE asset_rights ADD COLUMN review_status varchar(32) NOT NULL DEFAULT 'UNREVIEWED'",
    "ALTER TABLE asset_rights ADD CONSTRAINT ck_asset_rights_source_type CHECK (source_type IN ('USER_UPLOAD','GENERATED','LICENSED','PUBLIC_DOMAIN','THIRD_PARTY','UNKNOWN'))",
    "ALTER TABLE asset_rights ADD CONSTRAINT ck_asset_rights_license_type CHECK (license_type IN ('OWNED','COMMERCIAL_LICENSE','NONCOMMERCIAL','PUBLIC_DOMAIN','CC_BY','CC_BY_SA','UNKNOWN'))",
    "ALTER TABLE asset_rights ADD CONSTRAINT ck_asset_rights_commercial_use CHECK (commercial_use IN ('ALLOWED','DENIED','UNKNOWN'))",
    "ALTER TABLE asset_rights ADD CONSTRAINT ck_asset_rights_redistribution CHECK (redistribution IN ('ALLOWED','DENIED','UNKNOWN'))",
    "ALTER TABLE asset_rights ADD CONSTRAINT ck_asset_rights_training_use CHECK (training_use IN ('ALLOWED','DENIED','UNKNOWN'))",
    "ALTER TABLE asset_rights ADD CONSTRAINT ck_asset_rights_review_status CHECK (review_status IN ('UNREVIEWED','ASSERTED','VERIFIED','RESTRICTED'))",
    """
    CREATE TABLE asset_upload_sessions (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        file_id uuid NOT NULL,
        created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        status varchar(32) NOT NULL,
        upload_mode varchar(32) NOT NULL,
        bucket varchar(255) NOT NULL,
        object_key varchar(1024) NOT NULL,
        multipart_upload_id varchar(1024),
        declared_mime_type varchar(255) NOT NULL,
        declared_size bigint NOT NULL,
        expected_checksum_sha256 char(64) NOT NULL,
        expires_at timestamptz NOT NULL,
        completed_at timestamptz,
        verified_at timestamptz,
        verified_size bigint,
        verification_error_code varchar(100),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_asset_upload_sessions_file UNIQUE (file_id),
        CONSTRAINT uq_asset_upload_sessions_object UNIQUE (organization_id, bucket, object_key),
        CONSTRAINT ck_asset_upload_sessions_status CHECK (status IN ('pending','completed','expired','aborted','rejected')),
        CONSTRAINT ck_asset_upload_sessions_mode CHECK (upload_mode IN ('single','multipart')),
        CONSTRAINT ck_asset_upload_sessions_size CHECK (declared_size > 0 AND (verified_size IS NULL OR verified_size >= 0)),
        CONSTRAINT ck_asset_upload_sessions_checksum CHECK (expected_checksum_sha256 ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX ix_asset_upload_sessions_org_status_expiry ON asset_upload_sessions (organization_id, status, expires_at)",
    "CREATE INDEX ix_asset_upload_sessions_project_created ON asset_upload_sessions (project_id, created_at)",
    """
    CREATE TABLE asset_validation_runs (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        asset_file_id uuid NOT NULL REFERENCES asset_files(id) ON DELETE CASCADE,
        status varchar(32) NOT NULL,
        scanner_status varchar(32),
        sniffed_mime_type varchar(255),
        full_checksum_sha256 char(64),
        failure_code varchar(100),
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        started_at timestamptz,
        completed_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT ck_asset_validation_runs_status CHECK (status IN ('pending','running','succeeded','rejected','error')),
        CONSTRAINT ck_asset_validation_runs_scanner CHECK (scanner_status IS NULL OR scanner_status IN ('CLEAN','INFECTED','SCAN_UNAVAILABLE','ERROR')),
        CONSTRAINT ck_asset_validation_runs_checksum CHECK (full_checksum_sha256 IS NULL OR full_checksum_sha256 ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX ix_asset_validation_runs_org_asset ON asset_validation_runs (organization_id, asset_id, created_at)",
    "CREATE INDEX ix_asset_validation_runs_status_created ON asset_validation_runs (status, created_at)",
    """
    CREATE FUNCTION protect_asset_file_identity()
    RETURNS trigger AS $$
    BEGIN
        IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
           OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
           OR NEW.variant IS DISTINCT FROM OLD.variant
           OR NEW.bucket IS DISTINCT FROM OLD.bucket
           OR NEW.object_key IS DISTINCT FROM OLD.object_key
           OR NEW.checksum_sha256 IS DISTINCT FROM OLD.checksum_sha256
           OR NEW.mime_type IS DISTINCT FROM OLD.mime_type
           OR NEW.byte_size IS DISTINCT FROM OLD.byte_size THEN
            RAISE EXCEPTION 'asset file storage identity is immutable';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER trg_asset_files_identity_immutable
    BEFORE UPDATE ON asset_files
    FOR EACH ROW EXECUTE FUNCTION protect_asset_file_identity()
    """,
    "GRANT SELECT, INSERT, UPDATE ON asset_upload_sessions, asset_validation_runs TO lumi_app",
)

DOWNGRADE_STATEMENTS = (
    "DROP TRIGGER trg_asset_files_identity_immutable ON asset_files",
    "DROP FUNCTION protect_asset_file_identity()",
    "DROP TABLE asset_validation_runs",
    "DROP TABLE asset_upload_sessions",
    "ALTER TABLE asset_rights DROP CONSTRAINT ck_asset_rights_review_status",
    "ALTER TABLE asset_rights DROP CONSTRAINT ck_asset_rights_training_use",
    "ALTER TABLE asset_rights DROP CONSTRAINT ck_asset_rights_redistribution",
    "ALTER TABLE asset_rights DROP CONSTRAINT ck_asset_rights_commercial_use",
    "ALTER TABLE asset_rights DROP CONSTRAINT ck_asset_rights_license_type",
    "ALTER TABLE asset_rights DROP CONSTRAINT ck_asset_rights_source_type",
    "ALTER TABLE asset_rights DROP COLUMN review_status",
    "ALTER TABLE asset_rights DROP COLUMN source_reference",
    "ALTER TABLE asset_rights DROP COLUMN training_use",
    "ALTER TABLE asset_rights DROP COLUMN redistribution",
    "ALTER TABLE asset_rights DROP COLUMN commercial_use",
    "ALTER TABLE asset_rights DROP COLUMN license_type",
    "ALTER TABLE asset_rights DROP COLUMN owner_assertion",
    "ALTER TABLE asset_rights DROP COLUMN source_type",
    "ALTER TABLE assets DROP CONSTRAINT ck_assets_status",
    "ALTER TABLE assets DROP COLUMN rejection_code",
    "ALTER TABLE assets DROP COLUMN status",
)


def upgrade() -> None:
    _execute(UPGRADE_STATEMENTS)


def downgrade() -> None:
    _execute(DOWNGRADE_STATEMENTS)
