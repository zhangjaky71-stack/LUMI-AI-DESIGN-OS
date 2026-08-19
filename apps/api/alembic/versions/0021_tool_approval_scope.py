"""Bind canonical approvals to exact Tool Gateway requests.

Revision ID: 0021_tool_approval_scope
Revises: 0020_generation_operation_identity
Create Date: 2026-08-19
"""

from alembic import op

revision = "0021_tool_approval_scope"
down_revision = "0020_generation_operation_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE approvals
            ADD COLUMN task_id uuid REFERENCES tasks(id) ON DELETE CASCADE,
            ADD COLUMN tool_key varchar(320),
            ADD COLUMN tool_request_hash char(64)
        """
    )
    op.execute(
        """
        ALTER TABLE approvals
            ADD CONSTRAINT ck_approvals_tool_scope_complete CHECK (
                (task_id IS NULL AND tool_key IS NULL AND tool_request_hash IS NULL)
                OR
                (task_id IS NOT NULL AND agent_run_id IS NOT NULL
                 AND tool_key IS NOT NULL AND tool_request_hash IS NOT NULL)
            ),
            ADD CONSTRAINT ck_approvals_tool_request_hash CHECK (
                tool_request_hash IS NULL OR tool_request_hash ~ '^[0-9a-f]{64}$'
            )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_approvals_tool_request
        ON approvals (organization_id, task_id, tool_key, tool_request_hash)
        WHERE tool_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_approvals_tool_pending
        ON approvals (organization_id, project_id, agent_run_id, task_id, status)
        WHERE tool_key IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_approvals_tool_pending")
    op.execute("DROP INDEX IF EXISTS uq_approvals_tool_request")
    op.execute("ALTER TABLE approvals DROP CONSTRAINT IF EXISTS ck_approvals_tool_request_hash")
    op.execute("ALTER TABLE approvals DROP CONSTRAINT IF EXISTS ck_approvals_tool_scope_complete")
    op.execute(
        """
        ALTER TABLE approvals
            DROP COLUMN IF EXISTS tool_request_hash,
            DROP COLUMN IF EXISTS tool_key,
            DROP COLUMN IF EXISTS task_id
        """
    )
