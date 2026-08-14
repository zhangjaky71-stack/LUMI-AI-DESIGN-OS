from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Protocol
from uuid import UUID

from .contracts import (
    MemoryActorType,
    MemoryCandidate,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemorySourceRef,
    MemoryStatus,
)
from .errors import MemoryConflictError


class MemoryDbConnection(Protocol):
    async def execute(self, query: str, *args: object) -> str: ...
    async def fetch(self, query: str, *args: object) -> list[Any]: ...
    async def fetchrow(self, query: str, *args: object) -> Any | None: ...
    def transaction(self) -> AbstractAsyncContextManager[Any]: ...


ConnectionFactory = Callable[[], AbstractAsyncContextManager[MemoryDbConnection]]


class PostgresMemoryRepository:
    """Transaction factory. All multi-step memory writes must use transaction()."""

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self.connection_factory = connection_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PostgresMemoryRepositorySession]:
        async with self.connection_factory() as connection:
            async with connection.transaction():
                yield PostgresMemoryRepositorySession(connection)


class PostgresMemoryRepositorySession:
    def __init__(self, connection: MemoryDbConnection) -> None:
        self.connection = connection

    async def get(self, memory_id: UUID) -> MemoryRecord | None:
        row = await self.connection.fetchrow(
            "SELECT * FROM memory_records WHERE id=$1",
            memory_id,
        )
        return _record(row) if row is not None else None

    async def find_active_by_key(
        self,
        *,
        organization_id: UUID,
        scope_type: str,
        scope_id: str,
        kind: str,
        semantic_key: str,
    ) -> tuple[MemoryRecord, ...]:
        lock_key = f"{organization_id}:{scope_type}:{scope_id}:{kind}:{semantic_key}"
        await self.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            lock_key,
        )
        rows = await self.connection.fetch(
            """
            SELECT * FROM memory_records
            WHERE organization_id=$1 AND scope_type=$2 AND scope_id=$3
              AND kind=$4 AND semantic_key=$5 AND status='ACTIVE'
              AND deleted_at IS NULL AND (expires_at IS NULL OR expires_at > now())
            ORDER BY created_at DESC, id
            FOR UPDATE
            """,
            organization_id,
            scope_type,
            scope_id,
            kind,
            semantic_key,
        )
        return tuple(_record(row) for row in rows)

    async def list_active(self, *, organization_id: UUID) -> tuple[MemoryRecord, ...]:
        rows = await self.connection.fetch(
            """
            SELECT * FROM memory_records
            WHERE organization_id=$1 AND status='ACTIVE' AND deleted_at IS NULL
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY created_at DESC, id
            """,
            organization_id,
        )
        return tuple(_record(row) for row in rows)

    async def list_records(self, *, organization_id: UUID) -> tuple[MemoryRecord, ...]:
        rows = await self.connection.fetch(
            "SELECT * FROM memory_records WHERE organization_id=$1 ORDER BY created_at DESC, id",
            organization_id,
        )
        return tuple(_record(row) for row in rows)

    async def insert_record(self, record: MemoryRecord) -> MemoryRecord:
        await self.connection.execute(
            """
            INSERT INTO memory_records (
                id,organization_id,scope_type,scope_id,kind,semantic_key,content_hash,
                content_structured,summary,source_refs,confidence,status,created_by_type,
                created_by_id,last_confirmed_at,expires_at,valid_from,valid_to,supersedes_id,
                retention_hold,deleted_at,embedding_model,embedding_version,embedding_dimensions,
                embedding,metadata_json,created_at,updated_at,version
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10::jsonb,$11,$12,$13,$14,$15,$16,$17,$18,$19,
                $20,$21,$22,$23,$24,$25::vector,$26::jsonb,$27,$27,$28
            )
            """,
            record.memory_id,
            record.organization_id,
            record.scope_type.value,
            record.scope_id,
            record.kind.value,
            record.semantic_key,
            record.content_hash,
            json.dumps(record.content_structured, ensure_ascii=False, sort_keys=True),
            record.summary,
            json.dumps(
                [_source_payload(ref) for ref in record.source_refs],
                ensure_ascii=False,
                sort_keys=True,
            ),
            record.confidence,
            record.status.value,
            record.created_by_type.value,
            record.created_by_id,
            record.last_confirmed_at,
            record.expires_at,
            record.valid_from,
            record.valid_to,
            record.supersedes_id,
            record.retention_hold,
            record.deleted_at,
            record.embedding_model,
            record.embedding_version,
            len(record.embedding) if record.embedding is not None else None,
            _vector_literal(record.embedding),
            json.dumps(record.metadata, ensure_ascii=False, sort_keys=True, default=str),
            record.created_at,
            record.version,
        )
        return record

    async def update_record(self, record: MemoryRecord, *, expected_version: int) -> MemoryRecord:
        result = await self.connection.execute(
            """
            UPDATE memory_records SET
                content_hash=$2, content_structured=$3::jsonb, summary=$4, source_refs=$5::jsonb,
                confidence=$6, status=$7, last_confirmed_at=$8, expires_at=$9,
                valid_from=$10, valid_to=$11, supersedes_id=$12, retention_hold=$13,
                deleted_at=$14, embedding_model=$15, embedding_version=$16,
                embedding_dimensions=$17, embedding=$18::vector, metadata_json=$19::jsonb,
                updated_at=now(), version=version+1
            WHERE id=$1 AND version=$20
            """,
            record.memory_id,
            record.content_hash,
            json.dumps(record.content_structured, ensure_ascii=False, sort_keys=True),
            record.summary,
            json.dumps(
                [_source_payload(ref) for ref in record.source_refs],
                ensure_ascii=False,
                sort_keys=True,
            ),
            record.confidence,
            record.status.value,
            record.last_confirmed_at,
            record.expires_at,
            record.valid_from,
            record.valid_to,
            record.supersedes_id,
            record.retention_hold,
            record.deleted_at,
            record.embedding_model,
            record.embedding_version,
            len(record.embedding) if record.embedding is not None else None,
            _vector_literal(record.embedding),
            json.dumps(record.metadata, ensure_ascii=False, sort_keys=True, default=str),
            expected_version,
        )
        if not result.endswith(" 1"):
            raise MemoryConflictError("MEMORY_VERSION_CONFLICT")
        return record

    async def insert_candidate(self, candidate: MemoryCandidate, *, outcome: str, reason: str | None) -> None:
        if outcome in {"REJECT_SENSITIVE", "REJECT_SCOPE"}:
            raise MemoryConflictError("MEMORY_REJECTED_CONTENT_MUST_NOT_PERSIST")
        await self.connection.execute(
            """
            INSERT INTO memory_candidates (
                id,organization_id,scope_type,scope_id,kind,semantic_key,content_hash,
                content_structured,summary,source_refs,confidence,created_by_type,created_by_id,
                explicit_remember,temporal_coexistence,outcome,reason,expires_at,metadata_json
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10::jsonb,$11,$12,$13,$14,$15,$16,$17,$18,$19::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            candidate.candidate_id,
            candidate.organization_id,
            candidate.scope_type.value,
            candidate.scope_id,
            candidate.kind.value,
            candidate.semantic_key,
            candidate.content_hash,
            json.dumps(candidate.content_structured, ensure_ascii=False, sort_keys=True),
            candidate.summary,
            json.dumps(
                [_source_payload(ref) for ref in candidate.source_refs],
                ensure_ascii=False,
                sort_keys=True,
            ),
            candidate.confidence,
            candidate.created_by_type.value,
            candidate.created_by_id,
            candidate.explicit_remember,
            candidate.temporal_coexistence,
            outcome,
            reason,
            candidate.expires_at,
            json.dumps(candidate.metadata, ensure_ascii=False, sort_keys=True, default=str),
        )

    async def soft_delete(self, memory_id: UUID, *, deleted_at: datetime, expected_version: int) -> MemoryRecord:
        result = await self.connection.execute(
            """
            UPDATE memory_records
            SET status='DELETED', deleted_at=$2, updated_at=now(), version=version+1
            WHERE id=$1 AND version=$3 AND retention_hold=false
            """,
            memory_id,
            deleted_at,
            expected_version,
        )
        if not result.endswith(" 1"):
            raise MemoryConflictError("MEMORY_DELETE_VERSION_OR_RETENTION_CONFLICT")
        row = await self.connection.fetchrow("SELECT * FROM memory_records WHERE id=$1", memory_id)
        if row is None:
            raise MemoryConflictError("MEMORY_DELETE_MISSING")
        return _record(row)


def _record(row: Any) -> MemoryRecord:
    embedding = row["embedding"]
    return MemoryRecord(
        memory_id=row["id"],
        organization_id=row["organization_id"],
        scope_type=MemoryScope(row["scope_type"]),
        scope_id=row["scope_id"],
        kind=MemoryKind(row["kind"]),
        semantic_key=row["semantic_key"],
        content_structured=dict(row["content_structured"]),
        summary=row["summary"],
        source_refs=tuple(MemorySourceRef(**dict(item)) for item in row["source_refs"]),
        confidence=float(row["confidence"]),
        status=MemoryStatus(row["status"]),
        created_by_type=MemoryActorType(row["created_by_type"]),
        created_by_id=row["created_by_id"],
        created_at=row["created_at"],
        last_confirmed_at=row["last_confirmed_at"],
        expires_at=row["expires_at"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        supersedes_id=row["supersedes_id"],
        version=int(row["version"]),
        retention_hold=bool(row["retention_hold"]),
        deleted_at=row["deleted_at"],
        embedding=tuple(float(item) for item in embedding) if embedding is not None else None,
        embedding_model=row["embedding_model"],
        embedding_version=row["embedding_version"],
        metadata=dict(row["metadata_json"] or {}),
    )


def _source_payload(ref: MemorySourceRef) -> dict[str, str]:
    return {
        "source_type": ref.source_type,
        "source_id": ref.source_id,
        "version": ref.version,
        "content_hash": ref.content_hash,
    }


def _vector_literal(value: tuple[float, ...] | None) -> str | None:
    if value is None:
        return None
    return "[" + ",".join(format(float(item), ".10g") for item in value) + "]"
