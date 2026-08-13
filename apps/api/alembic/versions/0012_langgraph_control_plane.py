"""Add LangGraph control-plane registry and AgentRun control state.

Revision ID: 0012_langgraph_control_plane
Revises: 0011_cost_ledger_budget_quota
Create Date: 2026-08-13
"""

from alembic import op

revision = "0012_langgraph_control_plane"
down_revision = "0011_cost_ledger_budget_quota"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agent_graph_definitions (
            id uuid PRIMARY KEY,
            graph_key varchar(128) NOT NULL,
            graph_version varchar(100) NOT NULL,
            agent_config_version varchar(100) NOT NULL,
            description varchar(1000) NOT NULL,
            state_schema_version integer NOT NULL,
            input_schema_version integer NOT NULL DEFAULT 1,
            output_schema_version integer NOT NULL DEFAULT 1,
            interrupt_policy_version varchar(100) NOT NULL DEFAULT '1',
            content_hash char(64) NOT NULL,
            enabled boolean NOT NULL DEFAULT true,
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_agent_graph_definitions_identity UNIQUE (graph_key, graph_version),
            CONSTRAINT ck_agent_graph_definitions_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_agent_graph_definitions_schema_versions CHECK (
                state_schema_version >= 1 AND input_schema_version >= 1 AND output_schema_version >= 1
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_agent_graph_definitions_enabled ON agent_graph_definitions (enabled, graph_key)"
    )

    op.execute(
        """
        CREATE TABLE agent_run_control (
            agent_run_id uuid PRIMARY KEY REFERENCES agent_runs(id) ON DELETE CASCADE,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
            graph_key varchar(128) NOT NULL,
            graph_version varchar(100) NOT NULL,
            agent_config_version varchar(100) NOT NULL,
            graph_definition_hash char(64) NOT NULL,
            thread_id varchar(255) NOT NULL,
            control_status varchar(32) NOT NULL,
            checkpoint_id varchar(512),
            checkpoint_namespace varchar(1024) NOT NULL DEFAULT '',
            state_values_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            next_nodes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            interrupts_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            error_code varchar(128),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_agent_run_control_thread UNIQUE (organization_id, thread_id),
            CONSTRAINT ck_agent_run_control_hash CHECK (
                graph_definition_hash ~ '^[0-9a-f]{64}$'
            ),
            CONSTRAINT ck_agent_run_control_status CHECK (
                control_status IN ('pending','running','interrupted','succeeded','failed','cancelled')
            ),
            CONSTRAINT ck_agent_run_control_version CHECK (version >= 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_agent_run_control_org_status ON agent_run_control "
        "(organization_id, control_status, updated_at)"
    )
    op.execute(
        "CREATE INDEX ix_agent_run_control_project_status ON agent_run_control "
        "(project_id, control_status, updated_at)"
    )

    # 0002 gives broad default DML privileges to future lumi_migration tables. Graph
    # definitions are control-plane policy and runtime must never mutate them.
    op.execute("REVOKE INSERT, UPDATE, DELETE ON agent_graph_definitions FROM lumi_app")
    op.execute("REVOKE DELETE ON agent_run_control FROM lumi_app")
    op.execute("GRANT SELECT ON agent_graph_definitions TO lumi_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON agent_run_control TO lumi_app")


def downgrade() -> None:
    op.execute("DROP TABLE agent_run_control")
    op.execute("DROP TABLE agent_graph_definitions")
