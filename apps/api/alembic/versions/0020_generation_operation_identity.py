"""Enforce one canonical generation per organization operation.

Revision ID: 0020_generation_operation_identity
Revises: 0019_side_effect_provider_attempt_barrier
Create Date: 2026-08-19
"""

from __future__ import annotations

from alembic import op

revision = "0020_generation_operation_identity"
down_revision = "0019_side_effect_provider_attempt_barrier"
branch_labels = None
depends_on = None

_INDEX_NAME = "uq_generations_org_operation"


def upgrade() -> None:
    # Never repair or silently select a winner for historical duplicates. If the
    # invariant was already violated, release migration must stop for explicit
    # operator reconciliation before a unique identity can be trusted.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM generations
                WHERE operation_id IS NOT NULL
                GROUP BY organization_id, operation_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'GENERATION_OPERATION_DUPLICATES_REQUIRE_RECONCILIATION';
            END IF;
        END
        $$;
        """
    )
    op.create_index(
        _INDEX_NAME,
        "generations",
        ["organization_id", "operation_id"],
        unique=True,
        postgresql_where=op.inline_literal("operation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="generations")
