"""Create agent, task, generation, cost, idempotency and event schema.

Revision ID: 0002_workflow_platform_schema
Revises: 0001_domain_core_schema
Create Date: 2026-08-13
"""

from collections.abc import Iterable

from alembic import op

revision = "0002_workflow_platform_schema"
down_revision = "0001_domain_core_schema"
branch_labels = None
depends_on = None


def _execute(statements: Iterable[str]) -> None:
    for statement in statements:
        op.execute(statement)


UPGRADE_STATEMENTS = (
    """
    CREATE TABLE agent_runs (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        thread_id varchar(255) NOT NULL,
        graph_version varchar(100) NOT NULL,
        agent_config_version varchar(100) NOT NULL,
        status varchar(32) NOT NULL DEFAULT 'pending',
        budget_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        started_at timestamptz,
        finished_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_agent_runs_org_project ON agent_runs (organization_id, project_id)",
    "CREATE INDEX ix_agent_runs_project_created ON agent_runs (project_id, created_at)",
    "CREATE INDEX ix_agent_runs_project_status ON agent_runs (project_id, status)",
    """
    CREATE TABLE agent_run_steps (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        agent_run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
        sequence_number integer NOT NULL CHECK (sequence_number >= 0),
        step_type varchar(64) NOT NULL,
        status varchar(32) NOT NULL,
        input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        output_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        trace_ref varchar(512),
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_agent_run_steps_sequence UNIQUE (agent_run_id, sequence_number)
    )
    """,
    "CREATE INDEX ix_agent_run_steps_org_run ON agent_run_steps (organization_id, agent_run_id)",
    "CREATE INDEX ix_agent_run_steps_run_created ON agent_run_steps (agent_run_id, created_at)",
    """
    CREATE TABLE tasks (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        agent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
        parent_task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
        type varchar(100) NOT NULL,
        status varchar(32) NOT NULL DEFAULT 'pending',
        owner_agent_key varchar(100),
        input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        output_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        priority integer NOT NULL DEFAULT 100,
        attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
        budget_reserved numeric(20,8) NOT NULL DEFAULT 0 CHECK (budget_reserved >= 0),
        started_at timestamptz,
        finished_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_tasks_org_project ON tasks (organization_id, project_id)",
    "CREATE INDEX ix_tasks_project_status ON tasks (project_id, status)",
    "CREATE INDEX ix_tasks_agent_run_created ON tasks (agent_run_id, created_at)",
    "CREATE INDEX ix_tasks_schedule ON tasks (status, priority, created_at)",
    """
    CREATE TABLE task_dependencies (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        depends_on_task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_task_dependencies_no_self_loop CHECK (task_id <> depends_on_task_id),
        CONSTRAINT uq_task_dependencies_identity UNIQUE (task_id, depends_on_task_id)
    )
    """,
    "CREATE INDEX ix_task_dependencies_org_task ON task_dependencies (organization_id, task_id)",
    "CREATE INDEX ix_task_dependencies_depends_on ON task_dependencies (depends_on_task_id)",
    """
    CREATE TABLE approvals (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        artifact_version_id uuid REFERENCES artifact_versions(id) ON DELETE CASCADE,
        agent_run_id uuid REFERENCES agent_runs(id) ON DELETE CASCADE,
        requested_by uuid,
        decided_by uuid,
        status varchar(32) NOT NULL DEFAULT 'pending',
        reason varchar(2000),
        decided_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_approvals_org_project ON approvals (organization_id, project_id)",
    "CREATE INDEX ix_approvals_status_created ON approvals (status, created_at)",
    """
    CREATE TABLE idempotency_operations (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        idempotency_key varchar(512) NOT NULL,
        operation_type varchar(100) NOT NULL,
        status varchar(32) NOT NULL DEFAULT 'pending',
        request_hash varchar(128) NOT NULL,
        result_ref varchar(512),
        error_code varchar(64),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_idempotency_operations_org_key UNIQUE (organization_id, idempotency_key)
    )
    """,
    "CREATE INDEX ix_idempotency_operations_status_created ON idempotency_operations (status, created_at)",
    """
    CREATE TABLE generations (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
        agent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
        operation_id uuid REFERENCES idempotency_operations(id) ON DELETE RESTRICT,
        provider varchar(100) NOT NULL,
        model varchar(255) NOT NULL,
        capability varchar(100) NOT NULL,
        status varchar(32) NOT NULL DEFAULT 'pending',
        request_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_generations_org_project ON generations (organization_id, project_id)",
    "CREATE INDEX ix_generations_task_created ON generations (task_id, created_at)",
    "CREATE INDEX ix_generations_agent_run_created ON generations (agent_run_id, created_at)",
    "CREATE INDEX ix_generations_status_created ON generations (status, created_at)",
    """
    CREATE TABLE provider_requests (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        generation_id uuid REFERENCES generations(id) ON DELETE SET NULL,
        provider varchar(100) NOT NULL,
        model varchar(255) NOT NULL,
        provider_request_id varchar(512),
        status varchar(32) NOT NULL,
        latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
        usage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        error_code varchar(64),
        error_retryable boolean,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_provider_requests_native UNIQUE (provider, provider_request_id)
    )
    """,
    "CREATE INDEX ix_provider_requests_org_generation ON provider_requests (organization_id, generation_id)",
    "CREATE INDEX ix_provider_requests_native ON provider_requests (provider_request_id)",
    """
    CREATE TABLE cost_ledger (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
        task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
        agent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
        generation_id uuid REFERENCES generations(id) ON DELETE SET NULL,
        provider_request_id uuid REFERENCES provider_requests(id) ON DELETE SET NULL,
        reverses_entry_id uuid REFERENCES cost_ledger(id) ON DELETE RESTRICT,
        provider varchar(100),
        model varchar(255),
        entry_type varchar(64) NOT NULL,
        amount numeric(20,8) NOT NULL,
        currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
        quantity numeric(30,10),
        unit varchar(64),
        occurred_at timestamptz NOT NULL,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_cost_ledger_org_created ON cost_ledger (organization_id, created_at)",
    "CREATE INDEX ix_cost_ledger_project_created ON cost_ledger (project_id, created_at)",
    "CREATE INDEX ix_cost_ledger_generation ON cost_ledger (generation_id)",
    "CREATE INDEX ix_cost_ledger_provider_request ON cost_ledger (provider_request_id)",
    """
    CREATE TABLE usage_counters (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        period_key varchar(64) NOT NULL,
        metric varchar(100) NOT NULL,
        quantity numeric(30,10) NOT NULL,
        unit varchar(64) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_usage_counters_identity UNIQUE (organization_id, period_key, metric)
    )
    """,
    "CREATE INDEX ix_usage_counters_org_period ON usage_counters (organization_id, period_key)",
    """
    CREATE TABLE outbox_events (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        event_name varchar(150) NOT NULL,
        aggregate_type varchar(100) NOT NULL,
        aggregate_id uuid NOT NULL,
        schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version > 0),
        payload_json jsonb NOT NULL,
        published_at timestamptz,
        publish_attempts integer NOT NULL DEFAULT 0 CHECK (publish_attempts >= 0),
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_outbox_pending ON outbox_events (published_at, created_at)",
    "CREATE INDEX ix_outbox_org_created ON outbox_events (organization_id, created_at)",
    "CREATE INDEX ix_outbox_aggregate ON outbox_events (aggregate_type, aggregate_id)",
    """
    CREATE TABLE inbox_events (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        event_id uuid NOT NULL,
        consumer varchar(150) NOT NULL,
        processed_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_inbox_events_consumer_event UNIQUE (consumer, event_id)
    )
    """,
    "CREATE INDEX ix_inbox_org_created ON inbox_events (organization_id, created_at)",
    """
    CREATE TABLE audit_events (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        actor_type varchar(64) NOT NULL,
        actor_id uuid,
        action varchar(150) NOT NULL,
        target_type varchar(100) NOT NULL,
        target_id uuid,
        request_id varchar(128),
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX ix_audit_events_org_created ON audit_events (organization_id, created_at)",
    "CREATE INDEX ix_audit_events_actor_created ON audit_events (actor_id, created_at)",
    "CREATE INDEX ix_audit_events_target ON audit_events (target_type, target_id)",
    "GRANT SELECT ON ALL TABLES IN SCHEMA public TO lumi_app",
    """
    GRANT INSERT, UPDATE, DELETE ON
        users, organizations, organization_members, workspaces, workspace_members,
        auth_identities, sessions, brands, brand_palettes, brand_fonts, brand_logos,
        brand_rules, projects, project_members, assets, asset_files, asset_previews,
        asset_metadata, asset_embeddings, asset_rights, design_documents,
        artifact_branches, artifacts, agent_runs, tasks, approvals, generations,
        provider_requests, usage_counters, idempotency_operations, outbox_events
    TO lumi_app
    """,
    """
    GRANT INSERT ON
        design_document_versions, artifact_versions, artifact_edges, artifact_files,
        artifact_provenance, agent_run_steps, task_dependencies, cost_ledger,
        inbox_events, audit_events
    TO lumi_app
    """,
    """
    ALTER DEFAULT PRIVILEGES FOR ROLE lumi_migration IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lumi_app
    """,
)

DROP_TABLES = (
    "audit_events",
    "inbox_events",
    "outbox_events",
    "usage_counters",
    "cost_ledger",
    "provider_requests",
    "generations",
    "idempotency_operations",
    "approvals",
    "task_dependencies",
    "tasks",
    "agent_run_steps",
    "agent_runs",
)


def upgrade() -> None:
    _execute(UPGRADE_STATEMENTS)


def downgrade() -> None:
    for table in DROP_TABLES:
        op.execute(f"DROP TABLE {table}")
