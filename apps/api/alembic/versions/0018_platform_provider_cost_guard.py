"""Add the platform-wide daily provider-dollar hard stop.

Revision ID: 0018_platform_provider_cost_guard
Revises: 0017_knowledge_engine
"""

from __future__ import annotations

from alembic import op

revision = "0018_platform_provider_cost_guard"
down_revision = "0017_knowledge_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform_provider_cost_guard (
            policy_key varchar(64) PRIMARY KEY,
            daily_cap_usd numeric(20,8) NOT NULL,
            enabled boolean NOT NULL DEFAULT true,
            fail_closed boolean NOT NULL DEFAULT true,
            metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT ck_platform_provider_cost_guard_cap CHECK (daily_cap_usd > 0),
            CONSTRAINT ck_platform_provider_cost_guard_key CHECK (length(policy_key) BETWEEN 1 AND 64)
        )
        """
    )
    op.execute(
        """
        INSERT INTO platform_provider_cost_guard (
            policy_key, daily_cap_usd, enabled, fail_closed, metadata_json,
            created_at, updated_at, version
        ) VALUES (
            'platform', 100.00000000, true, true,
            '{"currency":"USD","period":"utc_day","source":"release_closure_p0"}'::jsonb,
            now(), now(), 1
        )
        """
    )

    # Runtime may read the policy but cannot silently raise/disable the hard stop.
    op.execute("REVOKE INSERT, UPDATE, DELETE ON platform_provider_cost_guard FROM lumi_app")
    op.execute("GRANT SELECT ON platform_provider_cost_guard TO lumi_app")


def downgrade() -> None:
    op.execute("DROP TABLE platform_provider_cost_guard")
