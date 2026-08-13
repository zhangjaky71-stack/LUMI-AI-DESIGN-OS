"""Harden lumi_app privileges and immutable history tables.

Revision ID: 0003_runtime_privilege_hardening
Revises: 0002_workflow_platform_schema
Create Date: 2026-08-13
"""

from collections.abc import Iterable

from alembic import op

revision = "0003_runtime_privilege_hardening"
down_revision = "0002_workflow_platform_schema"
branch_labels = None
depends_on = None


def _execute(statements: Iterable[str]) -> None:
    for statement in statements:
        op.execute(statement)


IMMUTABLE_TABLES = (
    "design_document_versions",
    "artifact_edges",
    "artifact_files",
    "artifact_provenance",
    "cost_ledger",
    "inbox_events",
    "audit_events",
)


def upgrade() -> None:
    _execute(
        (
            "REVOKE INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM lumi_app",
            "GRANT SELECT ON ALL TABLES IN SCHEMA public TO lumi_app",
            """
            GRANT INSERT, UPDATE, DELETE ON
                users, organizations, organization_members, workspaces, workspace_members,
                auth_identities, sessions, brands, brand_palettes, brand_fonts, brand_logos,
                brand_rules, project_members, asset_files, asset_previews, asset_metadata,
                asset_embeddings, asset_rights, design_documents, artifact_branches,
                artifacts, agent_runs, tasks, approvals, provider_requests, usage_counters,
                idempotency_operations
            TO lumi_app
            """,
            "GRANT INSERT, UPDATE ON projects, assets, generations, outbox_events TO lumi_app",
            "GRANT INSERT, UPDATE ON agent_run_steps TO lumi_app",
            "GRANT INSERT, DELETE ON task_dependencies TO lumi_app",
            "GRANT INSERT ON design_document_versions TO lumi_app",
            "GRANT INSERT ON artifact_versions TO lumi_app",
            "GRANT UPDATE (status, quality_score) ON artifact_versions TO lumi_app",
            "GRANT INSERT ON artifact_edges, artifact_files, artifact_provenance TO lumi_app",
            "GRANT INSERT ON cost_ledger, inbox_events, audit_events TO lumi_app",
            """
            ALTER DEFAULT PRIVILEGES FOR ROLE lumi_migration IN SCHEMA public
            REVOKE INSERT, UPDATE, DELETE ON TABLES FROM lumi_app
            """,
            """
            ALTER DEFAULT PRIVILEGES FOR ROLE lumi_migration IN SCHEMA public
            GRANT SELECT ON TABLES TO lumi_app
            """,
            """
            CREATE FUNCTION lumi_reject_immutable_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'immutable table % cannot be updated or deleted', TG_TABLE_NAME
                    USING ERRCODE = '55000';
            END;
            $$
            """,
        )
    )
    for table in IMMUTABLE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION lumi_reject_immutable_mutation()
            """
        )


def downgrade() -> None:
    for table in IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS lumi_reject_immutable_mutation()")
    op.execute("GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lumi_app")
