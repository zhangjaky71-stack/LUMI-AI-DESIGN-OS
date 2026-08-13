"""Upgrade idempotency operations into the paid side-effect correctness boundary.

Revision ID: 0009_idempotency_side_effects
Revises: 0008_queue_event_runtime
Create Date: 2026-08-13
"""

from alembic import op

revision = "0009_idempotency_side_effects"
down_revision = "0008_queue_event_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE idempotency_operations "
        "DROP CONSTRAINT uq_idempotency_operations_org_key"
    )
    op.execute(
        """
        ALTER TABLE idempotency_operations
            ADD COLUMN business_scope_id uuid,
            ADD COLUMN lease_owner varchar(200),
            ADD COLUMN lease_expires_at timestamptz,
            ADD COLUMN provider_request_id varchar(512),
            ADD COLUMN result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN response_status integer,
            ADD COLUMN error_category varchar(32),
            ADD COLUMN completed_at timestamptz,
            ADD COLUMN attempt_count integer NOT NULL DEFAULT 0,
            ADD COLUMN ambiguity_reason varchar(2000)
        """
    )
    op.execute("UPDATE idempotency_operations SET status = 'new' WHERE status = 'pending'")
    op.execute("ALTER TABLE idempotency_operations ALTER COLUMN status SET DEFAULT 'new'")
    op.execute(
        """
        ALTER TABLE idempotency_operations
            ADD CONSTRAINT uq_idempotency_operations_identity
                UNIQUE (organization_id, operation_type, idempotency_key),
            ADD CONSTRAINT ck_idempotency_operations_status
                CHECK (status IN (
                    'new', 'in_progress', 'succeeded', 'failed_retryable',
                    'failed_final', 'ambiguous'
                )),
            ADD CONSTRAINT ck_idempotency_operations_response_status
                CHECK (response_status IS NULL OR response_status BETWEEN 100 AND 599),
            ADD CONSTRAINT ck_idempotency_operations_error_category
                CHECK (error_category IS NULL OR error_category IN (
                    'transient', 'permanent', 'ambiguous'
                )),
            ADD CONSTRAINT ck_idempotency_operations_attempt_count
                CHECK (attempt_count >= 0)
        """
    )
    op.execute(
        "CREATE INDEX ix_idempotency_operations_lease "
        "ON idempotency_operations (status, lease_expires_at)"
    )
    op.execute(
        "ALTER TABLE cost_ledger ADD COLUMN operation_id uuid "
        "REFERENCES idempotency_operations(id) ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE cost_ledger ADD CONSTRAINT uq_cost_ledger_operation_entry "
        "UNIQUE (operation_id, entry_type)"
    )
    op.execute("CREATE INDEX ix_cost_ledger_operation ON cost_ledger (operation_id)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_cost_ledger_operation")
    op.execute("ALTER TABLE cost_ledger DROP CONSTRAINT uq_cost_ledger_operation_entry")
    op.execute("ALTER TABLE cost_ledger DROP COLUMN operation_id")
    op.execute("DROP INDEX ix_idempotency_operations_lease")
    op.execute(
        "ALTER TABLE idempotency_operations "
        "DROP CONSTRAINT ck_idempotency_operations_attempt_count, "
        "DROP CONSTRAINT ck_idempotency_operations_error_category, "
        "DROP CONSTRAINT ck_idempotency_operations_response_status, "
        "DROP CONSTRAINT ck_idempotency_operations_status, "
        "DROP CONSTRAINT uq_idempotency_operations_identity"
    )
    op.execute("ALTER TABLE idempotency_operations ALTER COLUMN status SET DEFAULT 'pending'")
    op.execute("UPDATE idempotency_operations SET status = 'pending'")
    op.execute(
        """
        ALTER TABLE idempotency_operations
            DROP COLUMN ambiguity_reason,
            DROP COLUMN attempt_count,
            DROP COLUMN completed_at,
            DROP COLUMN error_category,
            DROP COLUMN response_status,
            DROP COLUMN result_json,
            DROP COLUMN provider_request_id,
            DROP COLUMN lease_expires_at,
            DROP COLUMN lease_owner,
            DROP COLUMN business_scope_id,
            ADD CONSTRAINT uq_idempotency_operations_org_key
                UNIQUE (organization_id, idempotency_key)
        """
    )
