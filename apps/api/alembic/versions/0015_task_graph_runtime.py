"""NODE-33 durable Task Graph runtime.

Revision ID: 0015_task_graph_runtime
Revises: 0014_agent_registry_provenance
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_task_graph_runtime"
down_revision = "0014_agent_registry_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_graph_instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipe_id", sa.String(length=64), nullable=False),
        sa.Column("recipe_version", sa.String(length=64), nullable=False),
        sa.Column("recipe_definition_hash", sa.String(length=64), nullable=False),
        sa.Column("recipe_provenance_hash", sa.String(length=64), nullable=False),
        sa.Column("task_graph_template_hash", sa.String(length=64), nullable=False),
        sa.Column("provenance_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("recipe_budget_limit_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("task_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancelled_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("task_count > 0", name="ck_task_graph_instances_task_count"),
        sa.CheckConstraint("state_version > 0", name="ck_task_graph_instances_state_version"),
        sa.CheckConstraint("completed_count >= 0 AND completed_count <= task_count", name="ck_task_graph_instances_completed_count"),
    )
    op.create_index("ix_task_graph_instances_org_status", "task_graph_instances", ["organization_id", "status"])
    op.create_index("ix_task_graph_instances_agent_run", "task_graph_instances", ["agent_run_id", "created_at"])

    for column in (
        sa.Column("task_graph_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipe_step_id", sa.String(length=128), nullable=True),
        sa.Column("task_key", sa.String(length=255), nullable=True),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wait_reason", sa.String(length=255), nullable=True),
        sa.Column("external_ref", sa.String(length=1024), nullable=True),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("dynamic_depth", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("dynamic_child_limit", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("concurrency_group", sa.String(length=255), nullable=True),
        sa.Column("concurrency_limit", sa.SmallInteger(), nullable=True),
    ):
        op.add_column("tasks", column)
    op.create_foreign_key(
        "fk_tasks_task_graph_id_task_graph_instances",
        "tasks",
        "task_graph_instances",
        ["task_graph_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint("ck_tasks_state_version", "tasks", "state_version > 0")
    op.create_check_constraint("ck_tasks_progress", "tasks", "progress_total > 0 AND progress_current >= 0 AND progress_current <= progress_total")
    op.create_check_constraint("ck_tasks_dynamic_depth", "tasks", "dynamic_depth >= 0 AND dynamic_depth <= 4")
    op.create_check_constraint("ck_tasks_dynamic_child_limit", "tasks", "dynamic_child_limit >= 0 AND dynamic_child_limit <= 32")
    op.create_check_constraint("ck_tasks_concurrency_limit", "tasks", "concurrency_limit IS NULL OR (concurrency_limit >= 1 AND concurrency_limit <= 32)")
    op.create_index(
        "uq_tasks_graph_task_key",
        "tasks",
        ["task_graph_id", "task_key"],
        unique=True,
        postgresql_where=sa.text("task_graph_id IS NOT NULL AND task_key IS NOT NULL"),
    )
    op.create_index("ix_tasks_ready_claim", "tasks", ["task_graph_id", "status", "retry_not_before", "priority"])
    op.create_index("ix_tasks_lease_reap", "tasks", ["status", "lease_expires_at"])
    op.create_index("ix_tasks_concurrency_group", "tasks", ["task_graph_id", "concurrency_group", "status"])

    op.create_table(
        "task_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_graph_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_graph_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("logical_operation_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("error_category", sa.String(length=128), nullable=True),
        sa.Column("result_ref", sa.String(length=1024), nullable=True),
        sa.Column("cost_amount_usd", sa.Numeric(18, 6), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", "attempt_number", name="uq_task_attempts_task_number"),
        sa.CheckConstraint("attempt_number > 0", name="ck_task_attempts_number"),
        sa.CheckConstraint("cost_amount_usd IS NULL OR cost_amount_usd >= 0", name="ck_task_attempts_cost"),
    )
    op.create_index("ix_task_attempts_graph_created", "task_attempts", ["task_graph_id", "created_at"])
    op.create_index("ix_task_attempts_logical_operation", "task_attempts", ["logical_operation_key", "attempt_number"])

    op.execute("GRANT SELECT, INSERT, UPDATE ON task_graph_instances TO lumi_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON task_attempts TO lumi_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON task_attempts FROM lumi_app")
    op.execute("REVOKE ALL ON task_graph_instances FROM lumi_app")
    op.drop_index("ix_task_attempts_logical_operation", table_name="task_attempts")
    op.drop_index("ix_task_attempts_graph_created", table_name="task_attempts")
    op.drop_table("task_attempts")
    op.drop_index("ix_tasks_concurrency_group", table_name="tasks")
    op.drop_index("ix_tasks_lease_reap", table_name="tasks")
    op.drop_index("ix_tasks_ready_claim", table_name="tasks")
    op.drop_index("uq_tasks_graph_task_key", table_name="tasks")
    op.drop_constraint("ck_tasks_concurrency_limit", "tasks", type_="check")
    op.drop_constraint("ck_tasks_dynamic_child_limit", "tasks", type_="check")
    op.drop_constraint("ck_tasks_dynamic_depth", "tasks", type_="check")
    op.drop_constraint("ck_tasks_progress", "tasks", type_="check")
    op.drop_constraint("ck_tasks_state_version", "tasks", type_="check")
    op.drop_constraint("fk_tasks_task_graph_id_task_graph_instances", "tasks", type_="foreignkey")
    for column in (
        "concurrency_limit",
        "concurrency_group",
        "dynamic_child_limit",
        "dynamic_depth",
        "progress_total",
        "progress_current",
        "external_ref",
        "wait_reason",
        "retry_not_before",
        "heartbeat_at",
        "lease_expires_at",
        "lease_owner",
        "state_version",
        "task_key",
        "recipe_step_id",
        "task_graph_id",
    ):
        op.drop_column("tasks", column)
    op.drop_index("ix_task_graph_instances_agent_run", table_name="task_graph_instances")
    op.drop_index("ix_task_graph_instances_org_status", table_name="task_graph_instances")
    op.drop_table("task_graph_instances")
