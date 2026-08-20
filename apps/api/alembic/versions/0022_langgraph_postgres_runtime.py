"""Provision pinned LangGraph PostgreSQL checkpoint and store runtime tables.

Revision ID: 0022_langgraph_postgres_runtime
Revises: 0021_tool_approval_scope
Create Date: 2026-08-20

The schema matches the non-vector migrations used by
langgraph-checkpoint-postgres==3.1.2. Runtime services use the lumi_app role and
must never call the package setup() methods; schema mutation remains owned by
lumi_migration/Alembic.
"""

from alembic import op

revision = "0022_langgraph_postgres_runtime"
down_revision = "0021_tool_approval_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE checkpoint_migrations (
            v integer PRIMARY KEY
        )
        """
    )
    op.execute(
        """
        CREATE TABLE checkpoints (
            thread_id text NOT NULL,
            checkpoint_ns text NOT NULL DEFAULT '',
            checkpoint_id text NOT NULL,
            parent_checkpoint_id text,
            type text,
            checkpoint jsonb NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE checkpoint_blobs (
            thread_id text NOT NULL,
            checkpoint_ns text NOT NULL DEFAULT '',
            channel text NOT NULL,
            version text NOT NULL,
            type text NOT NULL,
            blob bytea,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE checkpoint_writes (
            thread_id text NOT NULL,
            checkpoint_ns text NOT NULL DEFAULT '',
            checkpoint_id text NOT NULL,
            task_id text NOT NULL,
            task_path text NOT NULL DEFAULT '',
            idx integer NOT NULL,
            channel text NOT NULL,
            type text,
            blob bytea NOT NULL,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        )
        """
    )
    op.execute("CREATE INDEX checkpoints_thread_id_idx ON checkpoints (thread_id)")
    op.execute("CREATE INDEX checkpoint_blobs_thread_id_idx ON checkpoint_blobs (thread_id)")
    op.execute("CREATE INDEX checkpoint_writes_thread_id_idx ON checkpoint_writes (thread_id)")
    op.execute(
        "INSERT INTO checkpoint_migrations (v) SELECT generate_series(0, 9)"
    )

    op.execute(
        """
        CREATE TABLE store_migrations (
            v integer PRIMARY KEY
        )
        """
    )
    op.execute(
        """
        CREATE TABLE store (
            prefix text NOT NULL,
            key text NOT NULL,
            value jsonb NOT NULL,
            created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
            updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
            expires_at timestamptz,
            ttl_minutes integer,
            PRIMARY KEY (prefix, key)
        )
        """
    )
    op.execute("CREATE INDEX store_prefix_idx ON store USING btree (prefix text_pattern_ops)")
    op.execute(
        """
        CREATE INDEX idx_store_expires_at ON store (expires_at)
        WHERE expires_at IS NOT NULL
        """
    )
    op.execute("INSERT INTO store_migrations (v) SELECT generate_series(0, 3)")

    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            checkpoints, checkpoint_blobs, checkpoint_writes, store
        TO lumi_app
        """
    )
    op.execute(
        """
        GRANT SELECT ON checkpoint_migrations, store_migrations
        TO lumi_app
        """
    )


def downgrade() -> None:
    op.execute("REVOKE ALL ON store_migrations, checkpoint_migrations FROM lumi_app")
    op.execute(
        """
        REVOKE ALL ON store, checkpoint_writes, checkpoint_blobs, checkpoints
        FROM lumi_app
        """
    )
    op.execute("DROP TABLE IF EXISTS store")
    op.execute("DROP TABLE IF EXISTS store_migrations")
    op.execute("DROP TABLE IF EXISTS checkpoint_writes")
    op.execute("DROP TABLE IF EXISTS checkpoint_blobs")
    op.execute("DROP TABLE IF EXISTS checkpoints")
    op.execute("DROP TABLE IF EXISTS checkpoint_migrations")
