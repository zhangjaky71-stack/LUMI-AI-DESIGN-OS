"""Persist a fail-closed barrier before paid provider side effects.

Revision ID: 0019_side_effect_provider_attempt_barrier
Revises: 0018_platform_provider_cost_guard
Create Date: 2026-08-19
"""

from __future__ import annotations

from alembic import op

revision = "0019_side_effect_provider_attempt_barrier"
down_revision = "0018_platform_provider_cost_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This timestamp is written before the outbound provider call. If the
    # process dies after the provider may have accepted the request but before
    # provider_request_id is durably bound, a later stale-lease claimant must
    # fail closed instead of executing the paid side effect again.
    op.execute(
        "ALTER TABLE idempotency_operations "
        "ADD COLUMN provider_attempt_started_at timestamptz"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE idempotency_operations "
        "DROP COLUMN provider_attempt_started_at"
    )
