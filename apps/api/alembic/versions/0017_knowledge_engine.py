"""NODE-36 versioned Knowledge Engine index.

Revision ID: 0017_knowledge_engine
Revises: 0016_memory_engine
"""

from __future__ import annotations

from alembic import op

revision = "0017_knowledge_engine"
down_revision = "0016_memory_engine"
branch_labels = None
depends_on = None


UPGRADE_STATEMENTS = (
    """
    CREATE TABLE knowledge_documents (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL
            REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid REFERENCES projects(id) ON DELETE CASCADE,
        permission_scope varchar(32) NOT NULL,
        source_type varchar(32) NOT NULL,
        source_id varchar(1024) NOT NULL,
        source_version varchar(255) NOT NULL,
        source_hash varchar(128) NOT NULL,
        title varchar(512),
        source_uri text,
        observed_at timestamptz,
        source_updated_at timestamptz,
        trust varchar(32) NOT NULL,
        status varchar(32) NOT NULL,
        normalized_text text NOT NULL,
        parser_version varchar(128) NOT NULL,
        chunker_version varchar(128) NOT NULL,
        index_version varchar(128) NOT NULL,
        language varchar(32),
        embedding_space_id varchar(255),
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_knowledge_documents_source UNIQUE (
            organization_id,
            source_type,
            source_id,
            source_version,
            source_hash,
            index_version
        ),
        CONSTRAINT ck_knowledge_documents_permission_scope CHECK (
            permission_scope IN ('PROJECT','ORGANIZATION')
        ),
        CONSTRAINT ck_knowledge_documents_project_scope CHECK (
            permission_scope <> 'PROJECT' OR project_id IS NOT NULL
        ),
        CONSTRAINT ck_knowledge_documents_source_type CHECK (
            source_type IN (
                'ASSET','URL','TEXT','ARTIFACT','INTERNAL_DOCUMENT'
            )
        ),
        CONSTRAINT ck_knowledge_documents_trust CHECK (
            trust IN (
                'INTERNAL_DATA','USER_CONTENT',
                'EXTERNAL_UNTRUSTED','MODEL_GENERATED'
            )
        ),
        CONSTRAINT ck_knowledge_documents_status CHECK (
            status IN (
                'PENDING','EXTRACTING','CHUNKING','EMBEDDING','READY',
                'FAILED','STALE','SUPERSEDED','DELETED'
            )
        ),
        CONSTRAINT ck_knowledge_documents_version CHECK (version > 0)
    )
    """,
    """
    CREATE INDEX ix_knowledge_documents_org_project_status
    ON knowledge_documents (organization_id, project_id, status)
    """,
    """
    CREATE INDEX ix_knowledge_documents_source_lookup
    ON knowledge_documents (
        organization_id, source_type, source_id, status
    )
    """,
    """
    CREATE TABLE knowledge_chunks (
        id uuid PRIMARY KEY,
        organization_id uuid NOT NULL
            REFERENCES organizations(id) ON DELETE CASCADE,
        project_id uuid REFERENCES projects(id) ON DELETE CASCADE,
        document_id uuid NOT NULL
            REFERENCES knowledge_documents(id) ON DELETE CASCADE,
        ordinal integer NOT NULL,
        content_hash char(64) NOT NULL,
        text text NOT NULL,
        token_estimate integer NOT NULL,
        locator_json jsonb NOT NULL,
        embedding_model varchar(255),
        embedding_version varchar(100),
        embedding_space_id varchar(255),
        embedding_dimensions integer,
        embedding vector,
        metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        version integer NOT NULL DEFAULT 1,
        CONSTRAINT uq_knowledge_chunks_document_ordinal UNIQUE (
            document_id, ordinal
        ),
        CONSTRAINT ck_knowledge_chunks_ordinal CHECK (ordinal >= 0),
        CONSTRAINT ck_knowledge_chunks_tokens CHECK (token_estimate > 0),
        CONSTRAINT ck_knowledge_chunks_content_hash CHECK (
            content_hash ~ '^[0-9a-f]{64}$'
        ),
        CONSTRAINT ck_knowledge_chunks_embedding CHECK (
            (
                embedding IS NULL
                AND embedding_model IS NULL
                AND embedding_version IS NULL
                AND embedding_space_id IS NULL
                AND embedding_dimensions IS NULL
            )
            OR
            (
                embedding IS NOT NULL
                AND embedding_model IS NOT NULL
                AND embedding_version IS NOT NULL
                AND embedding_space_id IS NOT NULL
                AND embedding_dimensions > 0
            )
        )
    )
    """,
    """
    CREATE INDEX ix_knowledge_chunks_org_project
    ON knowledge_chunks (organization_id, project_id, document_id)
    """,
    """
    CREATE INDEX ix_knowledge_chunks_document
    ON knowledge_chunks (document_id, ordinal)
    """,
    """
    GRANT SELECT, INSERT, UPDATE
    ON knowledge_documents, knowledge_chunks
    TO lumi_app
    """,
    """
    REVOKE DELETE
    ON knowledge_documents, knowledge_chunks
    FROM lumi_app
    """,
)

DOWNGRADE_STATEMENTS = (
    "DROP TABLE knowledge_chunks",
    "DROP TABLE knowledge_documents",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
