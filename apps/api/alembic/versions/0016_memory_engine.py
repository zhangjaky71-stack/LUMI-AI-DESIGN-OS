"""NODE-35 governed long-term Memory Engine.

Revision ID: 0016_memory_engine
Revises: 0015_task_graph_runtime
"""

from __future__ import annotations

from alembic import op

revision = "0016_memory_engine"
down_revision = "0015_task_graph_runtime"
branch_labels = None
depends_on = None


UPGRADE_STATEMENTS = (
    """
    CREATE TABLE memory_records (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL
            REFERENCES organizations(id) ON DELETE CASCADE,
        scope_type varchar(32) NOT NULL,
        scope_id varchar(512) NOT NULL,
        kind varchar(64) NOT NULL,
        semantic_key varchar(512) NOT NULL,
        content_hash char(64) NOT NULL,
        content_structured jsonb NOT NULL,
        summary text NOT NULL,
        source_refs jsonb NOT NULL,
        confidence double precision NOT NULL,
        status varchar(32) NOT NULL,
        created_by_type varchar(32) NOT NULL,
        created_by_id varchar(512) NOT NULL,
        last_confirmed_at timestamptz,
        expires_at timestamptz,
        valid_from timestamptz,
        valid_to timestamptz,
        supersedes_id uuid
            REFERENCES memory_records(id) ON DELETE RESTRICT,
        retention_hold boolean NOT NULL DEFAULT false,
        deleted_at timestamptz,
        embedding_model varchar(255),
        embedding_version varchar(100),
        embedding_dimensions integer,
        embedding vector,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT ck_memory_records_scope CHECK (
            scope_type IN (
                'SESSION','USER','PROJECT','BRAND','AGENT','ORGANIZATION'
            )
        ),
        CONSTRAINT ck_memory_records_kind CHECK (
            kind IN (
                'PREFERENCE','FACT','DECISION','CONSTRAINT_PREFERENCE',
                'WORKFLOW_LEARNING','EPISODIC_SUMMARY'
            )
        ),
        CONSTRAINT ck_memory_records_status CHECK (
            status IN (
                'ACTIVE','PENDING_CONFIRMATION','SUPERSEDED',
                'DELETED','EXPIRED','REJECTED'
            )
        ),
        CONSTRAINT ck_memory_records_actor CHECK (
            created_by_type IN ('USER','AGENT','SYSTEM')
        ),
        CONSTRAINT ck_memory_records_confidence CHECK (
            confidence >= 0 AND confidence <= 1
        ),
        CONSTRAINT ck_memory_records_version CHECK (version > 0),
        CONSTRAINT ck_memory_records_content_hash CHECK (
            content_hash ~ '^[0-9a-f]{64}$'
        ),
        CONSTRAINT ck_memory_records_embedding CHECK (
            (
                embedding IS NULL
                AND embedding_model IS NULL
                AND embedding_version IS NULL
                AND embedding_dimensions IS NULL
            )
            OR
            (
                embedding IS NOT NULL
                AND embedding_model IS NOT NULL
                AND embedding_version IS NOT NULL
                AND embedding_dimensions > 0
            )
        )
    )
    """,
    """
    CREATE INDEX ix_memory_records_org_scope
    ON memory_records (organization_id, scope_type, scope_id)
    """,
    """
    CREATE INDEX ix_memory_records_semantic_key
    ON memory_records (
        organization_id, scope_type, scope_id, kind, semantic_key
    )
    """,
    """
    CREATE INDEX ix_memory_records_active
    ON memory_records (organization_id, status, expires_at)
    """,
    """
    CREATE INDEX ix_memory_records_supersedes
    ON memory_records (supersedes_id)
    """,
    """
    CREATE TABLE memory_candidates (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL
            REFERENCES organizations(id) ON DELETE CASCADE,
        scope_type varchar(32) NOT NULL,
        scope_id varchar(512) NOT NULL,
        kind varchar(64) NOT NULL,
        semantic_key varchar(512) NOT NULL,
        content_hash char(64) NOT NULL,
        content_structured jsonb NOT NULL,
        summary text NOT NULL,
        source_refs jsonb NOT NULL,
        confidence double precision NOT NULL,
        created_by_type varchar(32) NOT NULL,
        created_by_id varchar(512) NOT NULL,
        explicit_remember boolean NOT NULL DEFAULT false,
        temporal_coexistence boolean NOT NULL DEFAULT false,
        outcome varchar(64) NOT NULL,
        reason varchar(255),
        expires_at timestamptz,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT ck_memory_candidates_scope CHECK (
            scope_type IN (
                'SESSION','USER','PROJECT','BRAND','AGENT','ORGANIZATION'
            )
        ),
        CONSTRAINT ck_memory_candidates_kind CHECK (
            kind IN (
                'PREFERENCE','FACT','DECISION','CONSTRAINT_PREFERENCE',
                'WORKFLOW_LEARNING','EPISODIC_SUMMARY'
            )
        ),
        CONSTRAINT ck_memory_candidates_actor CHECK (
            created_by_type IN ('USER','AGENT','SYSTEM')
        ),
        CONSTRAINT ck_memory_candidates_confidence CHECK (
            confidence >= 0 AND confidence <= 1
        ),
        CONSTRAINT ck_memory_candidates_outcome CHECK (
            outcome IN (
                'WRITE','DEDUPLICATE_CONFIRM','REQUIRE_CONFIRMATION',
                'BRAND_RULE_PROPOSAL'
            )
        ),
        CONSTRAINT ck_memory_candidates_content_hash CHECK (
            content_hash ~ '^[0-9a-f]{64}$'
        )
    )
    """,
    """
    CREATE INDEX ix_memory_candidates_org_outcome
    ON memory_candidates (organization_id, outcome, created_at)
    """,
    """
    CREATE INDEX ix_memory_candidates_scope_key
    ON memory_candidates (
        organization_id, scope_type, scope_id, semantic_key
    )
    """,
    """
    GRANT SELECT, INSERT, UPDATE
    ON memory_records, memory_candidates
    TO lumi_app
    """,
    """
    REVOKE DELETE
    ON memory_records, memory_candidates
    FROM lumi_app
    """,
)

DOWNGRADE_STATEMENTS = (
    "DROP TABLE memory_candidates",
    "DROP TABLE memory_records",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
