"""Add durable dead-letter records for queue/event runtime.

Revision ID: 0008_queue_event_runtime
Revises: 0007_asset_storage
Create Date: 2026-08-13
"""

from alembic import op

revision = "0008_queue_event_runtime"
down_revision = "0007_asset_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE dead_letter_records (
            id uuid PRIMARY KEY,
            organization_id uuid REFERENCES organizations(id) ON DELETE SET NULL,
            message_id uuid NOT NULL,
            message_kind varchar(32) NOT NULL,
            source_queue varchar(150) NOT NULL,
            consumer varchar(150),
            exchange_name varchar(150) NOT NULL,
            routing_key varchar(255) NOT NULL,
            error_category varchar(32) NOT NULL,
            error_code varchar(128) NOT NULL,
            error_message varchar(2000),
            attempts integer NOT NULL DEFAULT 1 CHECK (attempts >= 1),
            first_failed_at timestamptz NOT NULL DEFAULT now(),
            last_failed_at timestamptz NOT NULL DEFAULT now(),
            trace_id varchar(128),
            payload_json jsonb NOT NULL,
            replayed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT ck_dead_letter_records_message_kind
                CHECK (message_kind IN ('job', 'domain_event')),
            CONSTRAINT ck_dead_letter_records_error_category
                CHECK (error_category IN ('transient', 'permanent', 'cancelled'))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_dead_letter_records_queue_failure "
        "ON dead_letter_records (source_queue, last_failed_at)"
    )
    op.execute(
        "CREATE INDEX ix_dead_letter_records_org_failure "
        "ON dead_letter_records (organization_id, last_failed_at)"
    )
    op.execute("CREATE INDEX ix_dead_letter_records_message ON dead_letter_records (message_id)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON dead_letter_records TO lumi_app")


def downgrade() -> None:
    op.execute("DROP TABLE dead_letter_records")
