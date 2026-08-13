"""Bound LangGraph control metadata copies stored beside AgentRun state.

Revision ID: 0013_langgraph_control_plane_limits
Revises: 0012_langgraph_control_plane
Create Date: 2026-08-13
"""

from alembic import op

revision = "0013_langgraph_control_plane_limits"
down_revision = "0012_langgraph_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_run_control
            ADD CONSTRAINT ck_agent_run_control_state_size
                CHECK (octet_length(state_values_json::text) <= 1048576),
            ADD CONSTRAINT ck_agent_run_control_next_size
                CHECK (octet_length(next_nodes_json::text) <= 65536),
            ADD CONSTRAINT ck_agent_run_control_interrupt_size
                CHECK (octet_length(interrupts_json::text) <= 262144)
        """
    )
    op.execute(
        """
        ALTER TABLE agent_graph_definitions
            ADD CONSTRAINT ck_agent_graph_definitions_metadata_size
                CHECK (octet_length(metadata_json::text) <= 262144)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE agent_graph_definitions "
        "DROP CONSTRAINT ck_agent_graph_definitions_metadata_size"
    )
    op.execute(
        "ALTER TABLE agent_run_control DROP CONSTRAINT ck_agent_run_control_interrupt_size"
    )
    op.execute(
        "ALTER TABLE agent_run_control DROP CONSTRAINT ck_agent_run_control_next_size"
    )
    op.execute(
        "ALTER TABLE agent_run_control DROP CONSTRAINT ck_agent_run_control_state_size"
    )
