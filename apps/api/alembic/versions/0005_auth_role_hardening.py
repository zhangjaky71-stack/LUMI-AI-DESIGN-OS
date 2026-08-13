"""Normalize legacy organization roles and freeze RBAC role vocabulary.

Revision ID: 0005_auth_role_hardening
Revises: 0004_auth_security
Create Date: 2026-08-13
"""

from alembic import op

revision = "0005_auth_role_hardening"
down_revision = "0004_auth_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE organization_members
        SET role = upper(role)
        WHERE lower(role) IN ('owner','admin','editor','viewer','billing')
          AND role <> upper(role)
        """
    )
    op.execute(
        """
        ALTER TABLE organization_members
        ADD CONSTRAINT ck_organization_members_role
        CHECK (role IN ('OWNER','ADMIN','EDITOR','VIEWER','BILLING'))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE organization_members DROP CONSTRAINT ck_organization_members_role"
    )
