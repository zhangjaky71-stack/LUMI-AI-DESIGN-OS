"""Add Project Core brief history, summary projection and lifecycle hardening.

Revision ID: 0006_project_core
Revises: 0005_auth_role_hardening
Create Date: 2026-08-13
"""

from collections.abc import Iterable

from alembic import op

revision = "0006_project_core"
down_revision = "0005_auth_role_hardening"
branch_labels = None
depends_on = None


def _execute(statements: Iterable[str]) -> None:
    for statement in statements:
        op.execute(statement)


UPGRADE_STATEMENTS = (
    "ALTER TABLE projects ADD COLUMN brief_version integer NOT NULL DEFAULT 1",
    "ALTER TABLE projects ADD CONSTRAINT ck_projects_brief_version CHECK (brief_version > 0)",
    "ALTER TABLE projects ADD CONSTRAINT ck_projects_status CHECK (status IN ('draft','active','paused','archived'))",
    """
    CREATE TABLE project_brief_versions (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        brief_version integer NOT NULL,
        brief_hash char(64) NOT NULL,
        brief_json jsonb NOT NULL,
        source_input text,
        created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_project_brief_versions_project_version UNIQUE (project_id, brief_version),
        CONSTRAINT ck_project_brief_versions_version CHECK (brief_version > 0),
        CONSTRAINT ck_project_brief_versions_hash CHECK (brief_hash ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX ix_project_brief_versions_org_project ON project_brief_versions (organization_id, project_id, brief_version)",
    """
    CREATE TABLE project_summaries (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        latest_artifact_preview_id uuid,
        last_activity_at timestamptz NOT NULL DEFAULT now(),
        active_run_count integer NOT NULL DEFAULT 0,
        artifact_count integer NOT NULL DEFAULT 0,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_project_summaries_project UNIQUE (project_id),
        CONSTRAINT ck_project_summaries_active_runs CHECK (active_run_count >= 0),
        CONSTRAINT ck_project_summaries_artifacts CHECK (artifact_count >= 0)
    )
    """,
    "CREATE INDEX ix_project_summaries_org_activity ON project_summaries (organization_id, last_activity_at)",
    """
    CREATE FUNCTION reject_project_brief_version_mutation()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'project_brief_versions are immutable';
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER trg_project_brief_versions_immutable
    BEFORE UPDATE OR DELETE ON project_brief_versions
    FOR EACH ROW EXECUTE FUNCTION reject_project_brief_version_mutation()
    """,
    "GRANT SELECT, INSERT ON project_brief_versions TO lumi_app",
    "GRANT SELECT, INSERT, UPDATE ON project_summaries TO lumi_app",
)

DOWNGRADE_STATEMENTS = (
    "DROP TRIGGER trg_project_brief_versions_immutable ON project_brief_versions",
    "DROP FUNCTION reject_project_brief_version_mutation()",
    "DROP TABLE project_summaries",
    "DROP TABLE project_brief_versions",
    "ALTER TABLE projects DROP CONSTRAINT ck_projects_status",
    "ALTER TABLE projects DROP CONSTRAINT ck_projects_brief_version",
    "ALTER TABLE projects DROP COLUMN brief_version",
)


def upgrade() -> None:
    _execute(UPGRADE_STATEMENTS)


def downgrade() -> None:
    _execute(DOWNGRADE_STATEMENTS)
