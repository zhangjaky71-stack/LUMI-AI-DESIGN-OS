"""Add append-only Agent Registry provenance for AgentRun.

Revision ID: 0014_agent_registry_provenance
Revises: 0013_langgraph_control_plane_limits
Create Date: 2026-08-13
"""

from alembic import op

revision = "0014_agent_registry_provenance"
down_revision = "0013_langgraph_control_plane_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agent_run_provenance (
            agent_run_id uuid PRIMARY KEY REFERENCES agent_runs(id) ON DELETE CASCADE,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            requested_ref varchar(256) NOT NULL,
            agent_id varchar(64) NOT NULL,
            exact_version varchar(100) NOT NULL,
            release_status varchar(16) NOT NULL,
            definition_hash char(64) NOT NULL,
            system_prompt_hash char(64) NOT NULL,
            release_manifest_revision integer NOT NULL,
            provenance_hash char(64) NOT NULL,
            dependencies_json jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_agent_run_provenance_status CHECK (release_status IN ('DRAFT','CANDIDATE','PRODUCTION','DEPRECATED','DISABLED')),
            CONSTRAINT ck_agent_run_provenance_definition_hash CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_agent_run_provenance_prompt_hash CHECK (system_prompt_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_agent_run_provenance_hash CHECK (provenance_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_agent_run_provenance_revision CHECK (release_manifest_revision >= 1),
            CONSTRAINT ck_agent_run_provenance_dependencies_size CHECK (octet_length(dependencies_json::text) <= 1048576)
        )
        """
    )
    op.execute("CREATE INDEX ix_agent_run_provenance_org_agent ON agent_run_provenance (organization_id, agent_id, exact_version)")
    op.execute("CREATE INDEX ix_agent_run_provenance_project_created ON agent_run_provenance (project_id, created_at)")
    op.execute("REVOKE UPDATE, DELETE ON agent_run_provenance FROM lumi_app")
    op.execute("GRANT SELECT, INSERT ON agent_run_provenance TO lumi_app")


def downgrade() -> None:
    op.execute("DROP TABLE agent_run_provenance")
