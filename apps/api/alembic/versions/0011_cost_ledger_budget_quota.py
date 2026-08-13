"""Evolve provider cost truth, budget reservations, usage and quota controls.

Revision ID: 0011_cost_ledger_budget_quota
Revises: 0010_capability_registry
Create Date: 2026-08-13
"""

from alembic import op

revision = "0011_cost_ledger_budget_quota"
down_revision = "0010_capability_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cost_ledger DROP CONSTRAINT uq_cost_ledger_operation_entry")
    op.execute(
        """
        ALTER TABLE cost_ledger
            ADD COLUMN entry_key varchar(128) NOT NULL DEFAULT 'primary',
            ADD COLUMN pricing_snapshot_id varchar(128),
            ADD COLUMN external_provider_request_id varchar(512),
            ADD COLUMN confidence varchar(16) NOT NULL DEFAULT 'unknown',
            ADD COLUMN cost_basis varchar(32) NOT NULL DEFAULT 'provider_cost',
            ADD COLUMN source varchar(64) NOT NULL DEFAULT 'runtime',
            ADD CONSTRAINT ck_cost_ledger_confidence
                CHECK (confidence IN ('exact','estimated','unknown')),
            ADD CONSTRAINT ck_cost_ledger_cost_basis
                CHECK (cost_basis IN ('provider_cost','customer_charge')),
            ADD CONSTRAINT ck_cost_ledger_entry_key
                CHECK (length(entry_key) BETWEEN 1 AND 128),
            ADD CONSTRAINT ck_cost_ledger_quantity_nonnegative
                CHECK (quantity IS NULL OR quantity >= 0),
            ADD CONSTRAINT uq_cost_ledger_operation_entry_key
                UNIQUE (operation_id, entry_type, entry_key)
        """
    )
    op.execute(
        "CREATE INDEX ix_cost_ledger_org_occurred ON cost_ledger (organization_id, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_cost_ledger_org_type_occurred "
        "ON cost_ledger (organization_id, entry_type, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_cost_ledger_pricing_snapshot "
        "ON cost_ledger (pricing_snapshot_id) WHERE pricing_snapshot_id IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE cost_budget_limits (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            scope_type varchar(32) NOT NULL,
            scope_id uuid,
            period_key varchar(32) NOT NULL,
            amount_limit numeric(20,8) NOT NULL,
            currency char(3) NOT NULL DEFAULT 'USD',
            tolerance_amount numeric(20,8) NOT NULL DEFAULT 0,
            enabled boolean NOT NULL DEFAULT true,
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT ck_cost_budget_limits_scope_type CHECK (
                scope_type IN ('organization','project','agent_run','task','operation')
            ),
            CONSTRAINT ck_cost_budget_limits_scope_identity CHECK (
                (scope_type = 'organization' AND scope_id IS NULL)
                OR (scope_type <> 'organization' AND scope_id IS NOT NULL)
            ),
            CONSTRAINT ck_cost_budget_limits_period_key CHECK (length(period_key) BETWEEN 1 AND 32),
            CONSTRAINT ck_cost_budget_limits_amount CHECK (amount_limit >= 0),
            CONSTRAINT ck_cost_budget_limits_tolerance CHECK (tolerance_amount >= 0),
            CONSTRAINT ck_cost_budget_limits_currency CHECK (currency ~ '^[A-Z]{3}$')
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_cost_budget_limits_identity ON cost_budget_limits "
        "(organization_id, scope_type, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid), period_key, currency)"
    )
    op.execute(
        "CREATE INDEX ix_cost_budget_limits_org_scope ON cost_budget_limits "
        "(organization_id, scope_type, scope_id, period_key)"
    )

    op.execute(
        """
        CREATE TABLE cost_reservations (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            operation_id uuid NOT NULL REFERENCES idempotency_operations(id) ON DELETE RESTRICT,
            project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
            task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
            agent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
            generation_id uuid REFERENCES generations(id) ON DELETE SET NULL,
            provider varchar(100) NOT NULL,
            model varchar(255) NOT NULL,
            reservation_key varchar(512) NOT NULL,
            estimated_amount numeric(20,8) NOT NULL,
            actual_amount numeric(20,8),
            currency char(3) NOT NULL DEFAULT 'USD',
            pricing_snapshot_id varchar(128),
            confidence varchar(16) NOT NULL DEFAULT 'estimated',
            status varchar(32) NOT NULL DEFAULT 'active',
            expires_at timestamptz NOT NULL,
            committed_at timestamptz,
            released_at timestamptz,
            release_reason varchar(128),
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT uq_cost_reservations_identity UNIQUE (operation_id, reservation_key),
            CONSTRAINT ck_cost_reservations_estimate CHECK (estimated_amount >= 0),
            CONSTRAINT ck_cost_reservations_actual CHECK (actual_amount IS NULL OR actual_amount >= 0),
            CONSTRAINT ck_cost_reservations_currency CHECK (currency ~ '^[A-Z]{3}$'),
            CONSTRAINT ck_cost_reservations_confidence CHECK (
                confidence IN ('exact','estimated','unknown')
            ),
            CONSTRAINT ck_cost_reservations_status CHECK (
                status IN ('active','committed','released','expired')
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_cost_reservations_org_active ON cost_reservations "
        "(organization_id, status, expires_at)"
    )
    op.execute(
        "CREATE INDEX ix_cost_reservations_project_active ON cost_reservations "
        "(project_id, status, expires_at) WHERE project_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_cost_reservations_agent_run_active ON cost_reservations "
        "(agent_run_id, status, expires_at) WHERE agent_run_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_cost_reservations_task_active ON cost_reservations "
        "(task_id, status, expires_at) WHERE task_id IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE usage_ledger (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            operation_id uuid NOT NULL REFERENCES idempotency_operations(id) ON DELETE RESTRICT,
            cost_entry_id uuid REFERENCES cost_ledger(id) ON DELETE RESTRICT,
            project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
            task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
            agent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
            generation_id uuid REFERENCES generations(id) ON DELETE SET NULL,
            provider varchar(100),
            model varchar(255),
            external_provider_request_id varchar(512),
            metric varchar(100) NOT NULL,
            entry_key varchar(128) NOT NULL DEFAULT 'primary',
            quantity numeric(30,10) NOT NULL,
            unit varchar(64) NOT NULL,
            occurred_at timestamptz NOT NULL,
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_usage_ledger_operation_metric_key
                UNIQUE (operation_id, metric, entry_key),
            CONSTRAINT ck_usage_ledger_quantity CHECK (quantity >= 0),
            CONSTRAINT ck_usage_ledger_metric CHECK (length(metric) BETWEEN 1 AND 100),
            CONSTRAINT ck_usage_ledger_entry_key CHECK (length(entry_key) BETWEEN 1 AND 128)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_usage_ledger_org_occurred ON usage_ledger (organization_id, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_usage_ledger_project_occurred ON usage_ledger (project_id, occurred_at) "
        "WHERE project_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_usage_ledger_metric_occurred ON usage_ledger "
        "(organization_id, metric, occurred_at)"
    )

    op.execute(
        """
        CREATE TABLE quota_limits (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            scope_type varchar(32) NOT NULL DEFAULT 'organization',
            scope_id uuid,
            metric varchar(100) NOT NULL,
            period_key varchar(32) NOT NULL,
            quantity_limit numeric(30,10) NOT NULL,
            unit varchar(64) NOT NULL,
            enabled boolean NOT NULL DEFAULT true,
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT ck_quota_limits_scope_type CHECK (
                scope_type IN ('organization','project','agent_run')
            ),
            CONSTRAINT ck_quota_limits_scope_identity CHECK (
                (scope_type = 'organization' AND scope_id IS NULL)
                OR (scope_type <> 'organization' AND scope_id IS NOT NULL)
            ),
            CONSTRAINT ck_quota_limits_quantity CHECK (quantity_limit >= 0),
            CONSTRAINT ck_quota_limits_metric CHECK (length(metric) BETWEEN 1 AND 100),
            CONSTRAINT ck_quota_limits_period_key CHECK (length(period_key) BETWEEN 1 AND 32)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_quota_limits_identity ON quota_limits "
        "(organization_id, scope_type, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid), metric, period_key)"
    )
    op.execute(
        "CREATE INDEX ix_quota_limits_org_metric ON quota_limits "
        "(organization_id, metric, period_key)"
    )

    op.execute(
        """
        CREATE TABLE quota_leases (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            operation_id uuid NOT NULL REFERENCES idempotency_operations(id) ON DELETE RESTRICT,
            metric varchar(100) NOT NULL,
            quantity numeric(30,10) NOT NULL,
            unit varchar(64) NOT NULL,
            expires_at timestamptz NOT NULL,
            released_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_quota_leases_identity UNIQUE (organization_id, operation_id, metric),
            CONSTRAINT ck_quota_leases_quantity CHECK (quantity > 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_quota_leases_active ON quota_leases "
        "(organization_id, metric, expires_at) WHERE released_at IS NULL"
    )

    # 0002 established default DML privileges for future lumi_migration tables. NODE-27
    # explicitly narrows every new financial/control-plane table rather than relying on
    # GRANT statements to remove privileges that default privileges already supplied.
    op.execute("REVOKE UPDATE, DELETE ON cost_ledger FROM lumi_app")
    op.execute("REVOKE UPDATE, DELETE ON usage_ledger FROM lumi_app")
    op.execute("REVOKE DELETE ON cost_reservations FROM lumi_app")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON cost_budget_limits FROM lumi_app")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON quota_limits FROM lumi_app")
    op.execute("REVOKE DELETE ON quota_leases FROM lumi_app")
    op.execute("GRANT SELECT, INSERT ON usage_ledger TO lumi_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON cost_reservations TO lumi_app")
    op.execute("GRANT SELECT ON cost_budget_limits, quota_limits TO lumi_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON quota_leases TO lumi_app")


def downgrade() -> None:
    op.execute("DROP TABLE quota_leases")
    op.execute("DROP INDEX uq_quota_limits_identity")
    op.execute("DROP TABLE quota_limits")
    op.execute("DROP TABLE usage_ledger")
    op.execute("DROP TABLE cost_reservations")
    op.execute("DROP INDEX uq_cost_budget_limits_identity")
    op.execute("DROP TABLE cost_budget_limits")
    op.execute("DROP INDEX ix_cost_ledger_pricing_snapshot")
    op.execute("DROP INDEX ix_cost_ledger_org_type_occurred")
    op.execute("DROP INDEX ix_cost_ledger_org_occurred")
    op.execute("ALTER TABLE cost_ledger DROP CONSTRAINT uq_cost_ledger_operation_entry_key")
    op.execute("ALTER TABLE cost_ledger DROP CONSTRAINT ck_cost_ledger_quantity_nonnegative")
    op.execute("ALTER TABLE cost_ledger DROP CONSTRAINT ck_cost_ledger_entry_key")
    op.execute("ALTER TABLE cost_ledger DROP CONSTRAINT ck_cost_ledger_cost_basis")
    op.execute("ALTER TABLE cost_ledger DROP CONSTRAINT ck_cost_ledger_confidence")
    op.execute(
        """
        ALTER TABLE cost_ledger
            DROP COLUMN source,
            DROP COLUMN cost_basis,
            DROP COLUMN confidence,
            DROP COLUMN external_provider_request_id,
            DROP COLUMN pricing_snapshot_id,
            DROP COLUMN entry_key,
            ADD CONSTRAINT uq_cost_ledger_operation_entry UNIQUE (operation_id, entry_type)
        """
    )
