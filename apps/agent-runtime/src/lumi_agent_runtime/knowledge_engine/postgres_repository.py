from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Protocol
from uuid import UUID

from .contracts import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePermissionScope,
    KnowledgeSourceRef,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeTrust,
)


class KnowledgeDbConnection(Protocol):
    async def execute(self, query: str, *args: object) -> str: ...

    async def executemany(
        self,
        query: str,
        args: list[tuple[object, ...]],
    ) -> None: ...

    async def fetch(self, query: str, *args: object) -> list[Any]: ...

    async def fetchrow(self, query: str, *args: object) -> Any | None: ...

    def transaction(self) -> AbstractAsyncContextManager[Any]: ...


ConnectionFactory = Callable[[], AbstractAsyncContextManager[KnowledgeDbConnection]]


class PostgresKnowledgeRepository:
    """Creates transaction-scoped Knowledge repository sessions."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self.connection_factory = connection_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PostgresKnowledgeRepositorySession]:
        async with self.connection_factory() as connection:
            async with connection.transaction():
                yield PostgresKnowledgeRepositorySession(connection)


class PostgresKnowledgeRepositorySession:
    def __init__(self, connection: KnowledgeDbConnection) -> None:
        self.connection = connection

    async def acquire_source_lock(
        self,
        *,
        organization_id: UUID,
        source_type: str,
        source_id: str,
    ) -> None:
        key = f"{organization_id}:{source_type}:{source_id}"
        await self.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            key,
        )

    async def get_document(self, document_id: UUID) -> KnowledgeDocument | None:
        row = await self.connection.fetchrow(
            "SELECT * FROM knowledge_documents WHERE id=$1",
            document_id,
        )
        return _document(row) if row is not None else None

    async def find_ready_source_versions(
        self,
        *,
        organization_id: UUID,
        source_type: str,
        source_id: str,
    ) -> tuple[KnowledgeDocument, ...]:
        rows = await self.connection.fetch(
            """
            SELECT * FROM knowledge_documents
            WHERE organization_id=$1
              AND source_type=$2
              AND source_id=$3
              AND status='READY'
            ORDER BY updated_at DESC, id
            FOR UPDATE
            """,
            organization_id,
            source_type,
            source_id,
        )
        return tuple(_document(row) for row in rows)

    async def list_ready_chunks(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        include_organization_scope: bool,
    ) -> tuple[KnowledgeChunk, ...]:
        rows = await self.connection.fetch(
            """
            SELECT
                c.*,
                d.source_type AS d_source_type,
                d.source_id AS d_source_id,
                d.source_version AS d_source_version,
                d.source_hash AS d_source_hash,
                d.title AS d_title,
                d.source_uri AS d_source_uri,
                d.observed_at AS d_observed_at,
                d.source_updated_at AS d_source_updated_at,
                d.trust AS d_trust
            FROM knowledge_chunks c
            JOIN knowledge_documents d ON d.id=c.document_id
            WHERE d.organization_id=$1
              AND d.status='READY'
              AND (
                    ($2::uuid IS NOT NULL AND d.project_id=$2)
                    OR (
                        $3::boolean
                        AND d.project_id IS NULL
                        AND d.permission_scope='ORGANIZATION'
                    )
              )
            ORDER BY d.updated_at DESC, d.id, c.ordinal
            """,
            organization_id,
            project_id,
            include_organization_scope,
        )
        return tuple(_chunk(row) for row in rows)

    async def list_chunks(
        self,
        *,
        document_id: UUID,
    ) -> tuple[KnowledgeChunk, ...]:
        rows = await self.connection.fetch(
            """
            SELECT
                c.*,
                d.source_type AS d_source_type,
                d.source_id AS d_source_id,
                d.source_version AS d_source_version,
                d.source_hash AS d_source_hash,
                d.title AS d_title,
                d.source_uri AS d_source_uri,
                d.observed_at AS d_observed_at,
                d.source_updated_at AS d_source_updated_at,
                d.trust AS d_trust
            FROM knowledge_chunks c
            JOIN knowledge_documents d ON d.id=c.document_id
            WHERE c.document_id=$1
            ORDER BY c.ordinal
            """,
            document_id,
        )
        return tuple(_chunk(row) for row in rows)

    async def insert_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        await self.connection.execute(
            """
            INSERT INTO knowledge_documents (
                id, organization_id, project_id, permission_scope,
                source_type, source_id, source_version, source_hash,
                title, source_uri, observed_at, source_updated_at,
                trust, status, normalized_text, parser_version,
                chunker_version, index_version, language,
                embedding_space_id, metadata_json, version
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                $17,$18,$19,$20,$21::jsonb,$22
            )
            """,
            document.document_id,
            document.organization_id,
            document.project_id,
            document.permission_scope.value,
            document.source.source_type.value,
            document.source.source_id,
            document.source.version,
            document.source.content_hash,
            document.source.title,
            document.source.uri,
            document.source.observed_at,
            document.source.source_updated_at,
            document.trust.value,
            document.status.value,
            document.normalized_text,
            document.parser_version,
            document.chunker_version,
            document.index_version,
            document.language,
            document.embedding_space_id,
            json.dumps(document.metadata, ensure_ascii=False, sort_keys=True, default=str),
            document.version,
        )
        return document

    async def replace_document(
        self,
        document: KnowledgeDocument,
        *,
        expected_version: int,
    ) -> KnowledgeDocument:
        result = await self.connection.execute(
            """
            UPDATE knowledge_documents
            SET project_id=$2,
                permission_scope=$3,
                trust=$4,
                status=$5,
                normalized_text=$6,
                parser_version=$7,
                chunker_version=$8,
                index_version=$9,
                language=$10,
                embedding_space_id=$11,
                metadata_json=$12::jsonb,
                updated_at=now(),
                version=version+1
            WHERE id=$1 AND version=$13
            """,
            document.document_id,
            document.project_id,
            document.permission_scope.value,
            document.trust.value,
            document.status.value,
            document.normalized_text,
            document.parser_version,
            document.chunker_version,
            document.index_version,
            document.language,
            document.embedding_space_id,
            json.dumps(document.metadata, ensure_ascii=False, sort_keys=True, default=str),
            expected_version,
        )
        if not result.endswith(" 1"):
            raise ValueError("KNOWLEDGE_DOCUMENT_VERSION_CONFLICT")
        return document

    async def replace_chunks(
        self,
        document_id: UUID,
        chunks: tuple[KnowledgeChunk, ...],
    ) -> None:
        if any(chunk.document_id != document_id for chunk in chunks):
            raise ValueError("KNOWLEDGE_CHUNK_DOCUMENT_MISMATCH")
        if not chunks:
            raise ValueError("KNOWLEDGE_CHUNKS_EMPTY")
        rows = [_chunk_write_row(chunk) for chunk in chunks]
        await self.connection.executemany(
            """
            INSERT INTO knowledge_chunks (
                id, organization_id, project_id, document_id, ordinal,
                content_hash, text, token_estimate, locator_json,
                embedding_model, embedding_version, embedding_space_id,
                embedding_dimensions, embedding, metadata_json
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,$14::vector,$15::jsonb
            )
            ON CONFLICT (document_id, ordinal) DO UPDATE SET
                id=EXCLUDED.id,
                organization_id=EXCLUDED.organization_id,
                project_id=EXCLUDED.project_id,
                content_hash=EXCLUDED.content_hash,
                text=EXCLUDED.text,
                token_estimate=EXCLUDED.token_estimate,
                locator_json=EXCLUDED.locator_json,
                embedding_model=EXCLUDED.embedding_model,
                embedding_version=EXCLUDED.embedding_version,
                embedding_space_id=EXCLUDED.embedding_space_id,
                embedding_dimensions=EXCLUDED.embedding_dimensions,
                embedding=EXCLUDED.embedding,
                metadata_json=EXCLUDED.metadata_json,
                updated_at=now(),
                version=knowledge_chunks.version+1
            """,
            rows,
        )


def _document(row: Any) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id=row["id"],
        organization_id=row["organization_id"],
        project_id=row["project_id"],
        source=KnowledgeSourceRef(
            source_type=KnowledgeSourceType(row["source_type"]),
            source_id=row["source_id"],
            version=row["source_version"],
            content_hash=row["source_hash"],
            title=row["title"],
            uri=row["source_uri"],
            observed_at=row["observed_at"],
            source_updated_at=row["source_updated_at"],
        ),
        permission_scope=KnowledgePermissionScope(row["permission_scope"]),
        trust=KnowledgeTrust(row["trust"]),
        status=KnowledgeStatus(row["status"]),
        normalized_text=row["normalized_text"],
        parser_version=row["parser_version"],
        chunker_version=row["chunker_version"],
        index_version=row["index_version"],
        language=row["language"],
        embedding_space_id=row["embedding_space_id"],
        metadata=_decode_json(row["metadata_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        version=int(row["version"]),
    )


def _chunk(row: Any) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=row["id"],
        document_id=row["document_id"],
        organization_id=row["organization_id"],
        project_id=row["project_id"],
        ordinal=int(row["ordinal"]),
        text=row["text"],
        content_hash=row["content_hash"],
        token_estimate=int(row["token_estimate"]),
        locator=_decode_json(row["locator_json"]),
        source=KnowledgeSourceRef(
            source_type=KnowledgeSourceType(row["d_source_type"]),
            source_id=row["d_source_id"],
            version=row["d_source_version"],
            content_hash=row["d_source_hash"],
            title=row["d_title"],
            uri=row["d_source_uri"],
            observed_at=row["d_observed_at"],
            source_updated_at=row["d_source_updated_at"],
        ),
        trust=KnowledgeTrust(row["d_trust"]),
        embedding=_decode_vector(row["embedding"]),
        embedding_model=row["embedding_model"],
        embedding_version=row["embedding_version"],
        embedding_space_id=row["embedding_space_id"],
        metadata=_decode_json(row["metadata_json"]),
    )


def _chunk_write_row(chunk: KnowledgeChunk) -> tuple[object, ...]:
    return (
        chunk.chunk_id,
        chunk.organization_id,
        chunk.project_id,
        chunk.document_id,
        chunk.ordinal,
        chunk.content_hash,
        chunk.text,
        chunk.token_estimate,
        json.dumps(chunk.locator, ensure_ascii=False, sort_keys=True, default=str),
        chunk.embedding_model,
        chunk.embedding_version,
        chunk.embedding_space_id,
        len(chunk.embedding) if chunk.embedding is not None else None,
        _vector_literal(chunk.embedding),
        json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True, default=str),
    )


def _decode_json(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise ValueError("KNOWLEDGE_JSON_OBJECT_EXPECTED")
        return decoded
    return dict(value)  # type: ignore[arg-type]


def _decode_vector(value: object) -> tuple[float, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().removeprefix("[").removesuffix("]")
        if not text:
            return ()
        return tuple(float(item) for item in text.split(","))
    return tuple(float(item) for item in value)  # type: ignore[arg-type]


def _vector_literal(value: tuple[float, ...] | None) -> str | None:
    if value is None:
        return None
    return "[" + ",".join(format(float(item), ".10g") for item in value) + "]"
