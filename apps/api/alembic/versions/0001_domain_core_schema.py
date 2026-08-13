"""Create identity, project, asset, design and artifact schema.

Revision ID: 0001_domain_core_schema
Revises:
Create Date: 2026-08-13
"""

from collections.abc import Iterable

from alembic import op

revision = "0001_domain_core_schema"
down_revision = None
branch_labels = None
depends_on = None


def _execute(statements: Iterable[str]) -> None:
    for statement in statements:
        op.execute(statement)


UPGRADE_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    """
    CREATE TABLE users (
        id uuid PRIMARY KEY,
        email varchar(320) NOT NULL UNIQUE,
        display_name varchar(200) NOT NULL,
        status varchar(32) NOT NULL DEFAULT 'active',
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE organizations (
        id uuid PRIMARY KEY,
        name varchar(200) NOT NULL,
        slug varchar(100) NOT NULL UNIQUE,
        status varchar(32) NOT NULL DEFAULT 'active',
        plan varchar(64) NOT NULL DEFAULT 'free',
        settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE organization_members (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role varchar(32) NOT NULL,
        status varchar(32) NOT NULL DEFAULT 'active',
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_organization_members_organization_user UNIQUE (organization_id, user_id)
    )
    """,
    "CREATE INDEX ix_organization_members_org_status ON organization_members (organization_id, status)",
    """
    CREATE TABLE workspaces (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        name varchar(200) NOT NULL,
        slug varchar(100) NOT NULL,
        settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_workspaces_org_slug UNIQUE (organization_id, slug)
    )
    """,
    "CREATE INDEX ix_workspaces_org_created ON workspaces (organization_id, created_at)",
    """
    CREATE TABLE workspace_members (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role varchar(32) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_workspace_members_workspace_user UNIQUE (workspace_id, user_id)
    )
    """,
    "CREATE INDEX ix_workspace_members_org_workspace ON workspace_members (organization_id, workspace_id)",
    """
    CREATE TABLE auth_identities (
        id uuid PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        provider varchar(64) NOT NULL,
        subject varchar(512) NOT NULL,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_auth_identities_provider_subject UNIQUE (provider, subject)
    )
    """,
    "CREATE INDEX ix_auth_identities_user ON auth_identities (user_id)",
    """
    CREATE TABLE sessions (
        id uuid PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        organization_id uuid REFERENCES organizations(id) ON DELETE CASCADE,
        token_hash varchar(128) NOT NULL UNIQUE,
        expires_at timestamptz NOT NULL,
        revoked boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_sessions_user_expires ON sessions (user_id, expires_at)",
    "CREATE INDEX ix_sessions_org_expires ON sessions (organization_id, expires_at)",
    """
    CREATE TABLE brands (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        name varchar(200) NOT NULL,
        profile_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        tone_json jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_brands_org_created ON brands (organization_id, created_at)",
    """
    CREATE TABLE brand_palettes (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        brand_id uuid NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
        name varchar(100) NOT NULL,
        colors_json jsonb NOT NULL DEFAULT '[]'::jsonb,
        sort_order integer NOT NULL DEFAULT 0,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_brand_palettes_brand_name UNIQUE (brand_id, name)
    )
    """,
    "CREATE INDEX ix_brand_palettes_org_brand ON brand_palettes (organization_id, brand_id)",
    """
    CREATE TABLE brand_fonts (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        brand_id uuid NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
        family varchar(200) NOT NULL,
        source_asset_id uuid,
        usage_role varchar(64) NOT NULL DEFAULT 'body',
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_brand_fonts_org_brand ON brand_fonts (organization_id, brand_id)",
    """
    CREATE TABLE brand_logos (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        brand_id uuid NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
        asset_id uuid NOT NULL,
        variant varchar(64) NOT NULL DEFAULT 'primary',
        rules_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_brand_logos_org_brand ON brand_logos (organization_id, brand_id)",
    """
    CREATE TABLE brand_rules (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        brand_id uuid NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
        rule_type varchar(64) NOT NULL,
        severity varchar(32) NOT NULL,
        rule_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_brand_rules_org_brand ON brand_rules (organization_id, brand_id)",
    "CREATE INDEX ix_brand_rules_brand_type ON brand_rules (brand_id, rule_type)",
    """
    CREATE TABLE projects (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        name varchar(300) NOT NULL,
        status varchar(32) NOT NULL DEFAULT 'draft',
        brief_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        brand_id uuid REFERENCES brands(id) ON DELETE SET NULL,
        active_branch_id uuid,
        settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        deleted_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_projects_org_created ON projects (organization_id, created_at)",
    "CREATE INDEX ix_projects_org_status ON projects (organization_id, status)",
    "CREATE INDEX ix_projects_workspace_created ON projects (workspace_id, created_at)",
    """
    CREATE TABLE project_members (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role varchar(32) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_project_members_project_user UNIQUE (project_id, user_id)
    )
    """,
    "CREATE INDEX ix_project_members_org_project ON project_members (organization_id, project_id)",
    """
    CREATE TABLE assets (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
        kind varchar(64) NOT NULL,
        source varchar(64) NOT NULL DEFAULT 'upload',
        original_name varchar(512),
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        deleted_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_assets_org_created ON assets (organization_id, created_at)",
    "CREATE INDEX ix_assets_project_created ON assets (project_id, created_at)",
    "CREATE INDEX ix_assets_org_kind ON assets (organization_id, kind)",
    """
    CREATE TABLE asset_files (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        variant varchar(64) NOT NULL DEFAULT 'original',
        bucket varchar(255) NOT NULL,
        object_key varchar(1024) NOT NULL,
        checksum_sha256 varchar(64) NOT NULL,
        mime_type varchar(255) NOT NULL,
        byte_size bigint NOT NULL CHECK (byte_size >= 0),
        width integer CHECK (width IS NULL OR width > 0),
        height integer CHECK (height IS NULL OR height > 0),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_asset_files_asset_variant UNIQUE (asset_id, variant),
        CONSTRAINT uq_asset_files_object_key UNIQUE (organization_id, bucket, object_key)
    )
    """,
    "CREATE INDEX ix_asset_files_org_asset ON asset_files (organization_id, asset_id)",
    """
    CREATE TABLE asset_previews (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        asset_file_id uuid NOT NULL REFERENCES asset_files(id) ON DELETE CASCADE,
        preview_kind varchar(64) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_asset_previews_asset_kind UNIQUE (asset_id, preview_kind)
    )
    """,
    "CREATE INDEX ix_asset_previews_org_asset ON asset_previews (organization_id, asset_id)",
    """
    CREATE TABLE asset_metadata (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        namespace varchar(100) NOT NULL,
        data_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_asset_metadata_asset_namespace UNIQUE (asset_id, namespace)
    )
    """,
    "CREATE INDEX ix_asset_metadata_org_asset ON asset_metadata (organization_id, asset_id)",
    """
    CREATE TABLE asset_embeddings (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        embedding_model varchar(255) NOT NULL,
        embedding_version varchar(100) NOT NULL,
        content_hash varchar(128) NOT NULL,
        dimensions integer NOT NULL CHECK (dimensions > 0),
        embedding vector NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_asset_embeddings_identity UNIQUE (
            asset_id, embedding_model, embedding_version, content_hash
        )
    )
    """,
    "CREATE INDEX ix_asset_embeddings_org_asset ON asset_embeddings (organization_id, asset_id)",
    """
    CREATE TABLE asset_rights (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE UNIQUE,
        scope varchar(32) NOT NULL,
        source varchar(255) NOT NULL,
        attribution_required boolean NOT NULL DEFAULT false,
        expires_at timestamptz,
        policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_asset_rights_org_asset ON asset_rights (organization_id, asset_id)",
    """
    CREATE TABLE design_documents (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title varchar(300) NOT NULL,
        design_ir_version varchar(64) NOT NULL DEFAULT '1',
        active_version_id uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_design_documents_org_project ON design_documents (organization_id, project_id)",
    "CREATE INDEX ix_design_documents_project_created ON design_documents (project_id, created_at)",
    """
    CREATE TABLE design_document_versions (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        document_id uuid NOT NULL REFERENCES design_documents(id) ON DELETE CASCADE,
        version_number integer NOT NULL CHECK (version_number > 0),
        content_hash varchar(128) NOT NULL,
        design_ir_json jsonb NOT NULL,
        created_by uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_design_versions_number UNIQUE (document_id, version_number),
        CONSTRAINT uq_design_versions_hash UNIQUE (document_id, content_hash)
    )
    """,
    "CREATE INDEX ix_design_versions_org_document ON design_document_versions (organization_id, document_id)",
    """
    CREATE TABLE artifacts (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        kind varchar(64) NOT NULL,
        title varchar(300),
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_artifacts_org_project ON artifacts (organization_id, project_id)",
    "CREATE INDEX ix_artifacts_project_created ON artifacts (project_id, created_at)",
    "CREATE INDEX ix_artifacts_project_kind ON artifacts (project_id, kind)",
    """
    CREATE TABLE artifact_branches (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        artifact_id uuid NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        name varchar(120) NOT NULL,
        head_version_id uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_artifact_branches_artifact_name UNIQUE (artifact_id, name)
    )
    """,
    "CREATE INDEX ix_artifact_branches_org_project ON artifact_branches (organization_id, project_id)",
    "CREATE INDEX ix_artifact_branches_artifact ON artifact_branches (artifact_id)",
    """
    CREATE TABLE artifact_versions (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        artifact_id uuid NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        branch_id uuid NOT NULL REFERENCES artifact_branches(id) ON DELETE CASCADE,
        parent_version_id uuid REFERENCES artifact_versions(id) ON DELETE RESTRICT,
        version_number integer NOT NULL CHECK (version_number > 0),
        status varchar(32) NOT NULL DEFAULT 'draft',
        content_hash varchar(128) NOT NULL,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        quality_score double precision,
        created_by_type varchar(32) NOT NULL,
        created_by_id uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_artifact_versions_number UNIQUE (artifact_id, version_number),
        CONSTRAINT uq_artifact_versions_hash UNIQUE (artifact_id, content_hash)
    )
    """,
    "CREATE INDEX ix_artifact_versions_org_artifact ON artifact_versions (organization_id, artifact_id)",
    "CREATE INDEX ix_artifact_versions_branch_created ON artifact_versions (branch_id, created_at)",
    "CREATE INDEX ix_artifact_versions_status ON artifact_versions (organization_id, status)",
    """
    CREATE TABLE artifact_edges (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        from_artifact_version_id uuid NOT NULL REFERENCES artifact_versions(id) ON DELETE CASCADE,
        to_artifact_version_id uuid NOT NULL REFERENCES artifact_versions(id) ON DELETE CASCADE,
        edge_type varchar(64) NOT NULL,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_artifact_edges_no_self_loop CHECK (
            from_artifact_version_id <> to_artifact_version_id
        ),
        CONSTRAINT uq_artifact_edges_identity UNIQUE (
            from_artifact_version_id, to_artifact_version_id, edge_type
        )
    )
    """,
    "CREATE INDEX ix_artifact_edges_org_from ON artifact_edges (organization_id, from_artifact_version_id)",
    "CREATE INDEX ix_artifact_edges_org_to ON artifact_edges (organization_id, to_artifact_version_id)",
    """
    CREATE TABLE artifact_files (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        artifact_version_id uuid NOT NULL REFERENCES artifact_versions(id) ON DELETE CASCADE,
        format varchar(32) NOT NULL,
        bucket varchar(255) NOT NULL,
        object_key varchar(1024) NOT NULL,
        checksum_sha256 varchar(64) NOT NULL,
        mime_type varchar(255) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_artifact_files_version_format UNIQUE (artifact_version_id, format)
    )
    """,
    "CREATE INDEX ix_artifact_files_org_version ON artifact_files (organization_id, artifact_version_id)",
    """
    CREATE TABLE artifact_provenance (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        artifact_version_id uuid NOT NULL REFERENCES artifact_versions(id) ON DELETE CASCADE,
        source_type varchar(64) NOT NULL,
        source_id uuid,
        operation varchar(100) NOT NULL,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_artifact_provenance_org_version ON artifact_provenance (organization_id, artifact_version_id)",
    "CREATE INDEX ix_artifact_provenance_source ON artifact_provenance (source_type, source_id)",
)

DROP_TABLES = (
    "artifact_provenance",
    "artifact_files",
    "artifact_edges",
    "artifact_versions",
    "artifact_branches",
    "artifacts",
    "design_document_versions",
    "design_documents",
    "asset_rights",
    "asset_embeddings",
    "asset_metadata",
    "asset_previews",
    "asset_files",
    "assets",
    "project_members",
    "projects",
    "brand_rules",
    "brand_logos",
    "brand_fonts",
    "brand_palettes",
    "brands",
    "sessions",
    "auth_identities",
    "workspace_members",
    "workspaces",
    "organization_members",
    "organizations",
    "users",
)


def upgrade() -> None:
    _execute(UPGRADE_STATEMENTS)


def downgrade() -> None:
    for table in DROP_TABLES:
        op.execute(f"DROP TABLE {table}")
