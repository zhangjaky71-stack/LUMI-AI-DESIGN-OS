"""Add authentication credentials, secure tokens and session security fields.

Revision ID: 0004_auth_security
Revises: 0003_runtime_privilege_hardening
Create Date: 2026-08-13
"""

from collections.abc import Iterable

from alembic import op

revision = "0004_auth_security"
down_revision = "0003_runtime_privilege_hardening"
branch_labels = None
depends_on = None


def _execute(statements: Iterable[str]) -> None:
    for statement in statements:
        op.execute(statement)


UPGRADE_STATEMENTS = (
    "ALTER TABLE users ADD COLUMN email_verified_at timestamptz",
    "ALTER TABLE sessions ADD COLUMN last_seen_at timestamptz",
    "ALTER TABLE sessions ADD COLUMN revoked_at timestamptz",
    "ALTER TABLE sessions ADD COLUMN csrf_token_hash varchar(64)",
    "ALTER TABLE sessions ADD COLUMN user_agent_hash varchar(64)",
    "ALTER TABLE sessions ADD COLUMN ip_risk_metadata jsonb NOT NULL DEFAULT '{}'::jsonb",
    "UPDATE sessions SET revoked_at = now() WHERE revoked = true AND revoked_at IS NULL",
    """
    CREATE TABLE password_credentials (
        id uuid PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        password_hash varchar(512) NOT NULL,
        changed_at timestamptz NOT NULL DEFAULT now(),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_password_credentials_user UNIQUE (user_id),
        CONSTRAINT ck_password_credentials_argon2id CHECK (password_hash LIKE '$argon2id$%')
    )
    """,
    """
    CREATE TABLE email_verification_tokens (
        id uuid PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash char(64) NOT NULL,
        expires_at timestamptz NOT NULL,
        consumed_at timestamptz,
        revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_email_verification_tokens_hash UNIQUE (token_hash),
        CONSTRAINT ck_email_verification_tokens_hash CHECK (token_hash ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX ix_email_verification_tokens_user_expires ON email_verification_tokens (user_id, expires_at)",
    """
    CREATE TABLE password_reset_tokens (
        id uuid PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash char(64) NOT NULL,
        expires_at timestamptz NOT NULL,
        consumed_at timestamptz,
        revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_password_reset_tokens_hash UNIQUE (token_hash),
        CONSTRAINT ck_password_reset_tokens_hash CHECK (token_hash ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX ix_password_reset_tokens_user_expires ON password_reset_tokens (user_id, expires_at)",
    """
    CREATE TABLE organization_invites (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        email varchar(320) NOT NULL,
        role varchar(32) NOT NULL,
        token_hash char(64) NOT NULL,
        invited_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        expires_at timestamptz NOT NULL,
        consumed_at timestamptz,
        revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_organization_invites_hash UNIQUE (token_hash),
        CONSTRAINT ck_organization_invites_hash CHECK (token_hash ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_organization_invites_role CHECK (role IN ('OWNER','ADMIN','EDITOR','VIEWER','BILLING'))
    )
    """,
    "CREATE INDEX ix_organization_invites_org_email ON organization_invites (organization_id, email)",
    "CREATE INDEX ix_organization_invites_expires ON organization_invites (expires_at)",
    """
    CREATE TABLE api_tokens (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        name varchar(200) NOT NULL,
        prefix varchar(32) NOT NULL,
        secret_hash char(64) NOT NULL,
        scopes jsonb NOT NULL,
        expires_at timestamptz,
        last_used_at timestamptz,
        revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_api_tokens_prefix UNIQUE (prefix),
        CONSTRAINT uq_api_tokens_hash UNIQUE (secret_hash),
        CONSTRAINT ck_api_tokens_hash CHECK (secret_hash ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX ix_api_tokens_org_created ON api_tokens (organization_id, created_at)",
    "CREATE INDEX ix_api_tokens_org_active ON api_tokens (organization_id, revoked_at, expires_at)",
    "GRANT SELECT ON password_credentials, email_verification_tokens, password_reset_tokens, organization_invites, api_tokens TO lumi_app",
    "GRANT INSERT, UPDATE ON password_credentials, email_verification_tokens, password_reset_tokens, organization_invites, api_tokens TO lumi_app",
)

DOWNGRADE_STATEMENTS = (
    "DROP TABLE api_tokens",
    "DROP TABLE organization_invites",
    "DROP TABLE password_reset_tokens",
    "DROP TABLE email_verification_tokens",
    "DROP TABLE password_credentials",
    "ALTER TABLE sessions DROP COLUMN ip_risk_metadata",
    "ALTER TABLE sessions DROP COLUMN user_agent_hash",
    "ALTER TABLE sessions DROP COLUMN csrf_token_hash",
    "ALTER TABLE sessions DROP COLUMN revoked_at",
    "ALTER TABLE sessions DROP COLUMN last_seen_at",
    "ALTER TABLE users DROP COLUMN email_verified_at",
)


def upgrade() -> None:
    _execute(UPGRADE_STATEMENTS)


def downgrade() -> None:
    _execute(DOWNGRADE_STATEMENTS)
