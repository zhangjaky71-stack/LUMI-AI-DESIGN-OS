from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid5

import asyncpg
from lumi_image_generation.model import GenerationJob, ImageGenerationSpec
from lumi_image_generation.ports import PendingInvocationRecord
from lumi_image_generation.repository import (
    GenerationRepositoryError,
    OperationSemanticConflict,
)

from .image_generation_codec import (
    SNAPSHOT_SCHEMA_VERSION,
    decode_result_snapshot,
    decode_spec,
    encode_result_snapshot,
    encode_spec,
)

_PROVIDER_PENDING = "model-gateway"
_MODEL_PENDING = "routing-pending"
_CAPABILITY = "image.generate"


class PostgresGenerationRepository:
    """Durable NODE-46 repository over the canonical `generations` table.

    The relational row is the lookup/control record. Full versioned NODE-46
    snapshots live in request_json/result_json so restart/replay never depends
    on process memory. Provider binary output is deliberately excluded.
    """

    def __init__(self, database_dsn: str) -> None:
        self.dsn = _asyncpg_dsn(database_dsn)

    async def get_by_operation(
        self,
        organization_id: str,
        operation_id: str,
    ) -> GenerationJob | None:
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await _single_operation_row(
                connection,
                organization_id=organization_id,
                operation_id=operation_id,
                for_update=False,
            )
            if row is None:
                return None
            return _job_from_result(row["result_json"])
        finally:
            await connection.close()

    async def save(self, job: GenerationJob) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await _lock_operation(connection, job.organization_id, job.operation_id)
                row = await _single_operation_row(
                    connection,
                    organization_id=job.organization_id,
                    operation_id=job.operation_id,
                    for_update=True,
                )
                if row is None:
                    raise GenerationRepositoryError("GENERATION_SPEC_SNAPSHOT_MISSING")
                spec = decode_spec(_json_object(row["request_json"]))
                if spec.semantic_hash != job.semantic_hash:
                    raise OperationSemanticConflict("GENERATION_OPERATION_SEMANTIC_CONFLICT")
                pending: dict[str, PendingInvocationRecord] = {}
                existing = _optional_result_snapshot(row["result_json"])
                if existing is not None:
                    existing_job, pending = existing
                    if existing_job.semantic_hash != job.semantic_hash:
                        raise OperationSemanticConflict(
                            "GENERATION_OPERATION_SEMANTIC_CONFLICT"
                        )
                    if existing_job.generation_id != job.generation_id:
                        raise GenerationRepositoryError(
                            "GENERATION_OPERATION_REBOUND_FORBIDDEN"
                        )
                provider, model = _job_provider_model(
                    job,
                    fallback_provider=str(row["provider"]),
                    fallback_model=str(row["model"]),
                )
                await connection.execute(
                    """
                    UPDATE generations
                    SET provider = $3,
                        model = $4,
                        capability = $5,
                        status = $6,
                        result_json = $7::jsonb
                    WHERE id = $1 AND organization_id = $2
                    """,
                    row["id"],
                    UUID(job.organization_id),
                    provider,
                    model,
                    _CAPABILITY,
                    job.status.casefold(),
                    _json_dump(encode_result_snapshot(job, pending)),
                )
        finally:
            await connection.close()

    async def get(self, organization_id: str, generation_id: str) -> GenerationJob | None:
        connection = await asyncpg.connect(self.dsn)
        try:
            rows = await connection.fetch(
                """
                SELECT id, organization_id, operation_id, provider, model,
                       request_json, result_json
                FROM generations
                WHERE organization_id = $1
                  AND result_json -> 'job' ->> 'generation_id' = $2
                ORDER BY created_at, id
                LIMIT 2
                """,
                UUID(organization_id),
                generation_id,
            )
            if len(rows) > 1:
                raise GenerationRepositoryError("GENERATION_LOGICAL_ID_DUPLICATE")
            if not rows:
                return None
            job = _job_from_result(rows[0]["result_json"])
            if job is None:
                raise GenerationRepositoryError("GENERATION_RESULT_SNAPSHOT_MISSING")
            return job
        finally:
            await connection.close()

    async def save_spec(self, spec: ImageGenerationSpec) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await _lock_operation(connection, spec.organization_id, spec.operation_id)
                row = await _single_operation_row(
                    connection,
                    organization_id=spec.organization_id,
                    operation_id=spec.operation_id,
                    for_update=True,
                )
                encoded = encode_spec(spec)
                if row is not None:
                    existing = decode_spec(_json_object(row["request_json"]))
                    if existing.semantic_hash != spec.semantic_hash:
                        raise OperationSemanticConflict(
                            "GENERATION_OPERATION_SPEC_CONFLICT"
                        )
                    return
                await connection.execute(
                    """
                    INSERT INTO generations (
                        id, organization_id, project_id, task_id, agent_run_id,
                        operation_id, provider, model, capability, status,
                        request_json, result_json
                    ) VALUES (
                        $1, $2, $3, $4, $5,
                        $6, $7, $8, $9, 'pending',
                        $10::jsonb, '{}'::jsonb
                    )
                    """,
                    _row_id(spec.organization_id, spec.operation_id),
                    UUID(spec.organization_id),
                    UUID(spec.project_id),
                    UUID(spec.task_id),
                    _optional_uuid(spec.agent_run_id),
                    UUID(spec.operation_id),
                    _PROVIDER_PENDING,
                    _MODEL_PENDING,
                    _CAPABILITY,
                    _json_dump(encoded),
                )
        finally:
            await connection.close()

    async def get_spec(
        self,
        organization_id: str,
        operation_id: str,
    ) -> ImageGenerationSpec | None:
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await _single_operation_row(
                connection,
                organization_id=organization_id,
                operation_id=operation_id,
                for_update=False,
            )
            if row is None:
                return None
            return decode_spec(_json_object(row["request_json"]))
        finally:
            await connection.close()

    async def save_pending(self, record: PendingInvocationRecord) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                row = await _logical_generation_row(
                    connection,
                    organization_id=record.organization_id,
                    generation_id=record.generation_id,
                    for_update=True,
                )
                if row is None:
                    raise GenerationRepositoryError("GENERATION_JOB_NOT_FOUND")
                job, pending = _required_result_snapshot(row["result_json"])
                existing = pending.get(record.candidate_id)
                if existing is not None:
                    if (
                        existing.result.provider_request_id
                        != record.result.provider_request_id
                    ):
                        raise GenerationRepositoryError(
                            "PENDING_INVOCATION_PROVIDER_REQUEST_CHANGED"
                        )
                    if (
                        existing.request.variant_operation_id
                        != record.request.variant_operation_id
                    ):
                        raise GenerationRepositoryError(
                            "PENDING_INVOCATION_OPERATION_CHANGED"
                        )
                pending[record.candidate_id] = record
                await _write_result_snapshot(connection, row, job, pending)
        finally:
            await connection.close()

    async def get_pending(
        self,
        organization_id: str,
        generation_id: str,
        candidate_id: str,
    ) -> PendingInvocationRecord | None:
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await _logical_generation_row(
                connection,
                organization_id=organization_id,
                generation_id=generation_id,
                for_update=False,
            )
            if row is None:
                return None
            _, pending = _required_result_snapshot(row["result_json"])
            return pending.get(candidate_id)
        finally:
            await connection.close()

    async def delete_pending(
        self,
        organization_id: str,
        generation_id: str,
        candidate_id: str,
    ) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                row = await _logical_generation_row(
                    connection,
                    organization_id=organization_id,
                    generation_id=generation_id,
                    for_update=True,
                )
                if row is None:
                    return
                job, pending = _required_result_snapshot(row["result_json"])
                if candidate_id not in pending:
                    return
                pending.pop(candidate_id)
                await _write_result_snapshot(connection, row, job, pending)
        finally:
            await connection.close()


async def _single_operation_row(
    connection: asyncpg.Connection,
    *,
    organization_id: str,
    operation_id: str,
    for_update: bool,
) -> asyncpg.Record | None:
    lock = " FOR UPDATE" if for_update else ""
    rows = await connection.fetch(
        """
        SELECT id, organization_id, project_id, task_id, agent_run_id,
               operation_id, provider, model, capability, status,
               request_json, result_json, created_at
        FROM generations
        WHERE organization_id = $1 AND operation_id = $2
        ORDER BY created_at, id
        LIMIT 2
        """
        + lock,
        UUID(organization_id),
        UUID(operation_id),
    )
    if len(rows) > 1:
        raise GenerationRepositoryError("GENERATION_OPERATION_DUPLICATE")
    return rows[0] if rows else None


async def _logical_generation_row(
    connection: asyncpg.Connection,
    *,
    organization_id: str,
    generation_id: str,
    for_update: bool,
) -> asyncpg.Record | None:
    lock = " FOR UPDATE" if for_update else ""
    rows = await connection.fetch(
        """
        SELECT id, organization_id, operation_id, provider, model,
               request_json, result_json
        FROM generations
        WHERE organization_id = $1
          AND result_json -> 'job' ->> 'generation_id' = $2
        ORDER BY created_at, id
        LIMIT 2
        """
        + lock,
        UUID(organization_id),
        generation_id,
    )
    if len(rows) > 1:
        raise GenerationRepositoryError("GENERATION_LOGICAL_ID_DUPLICATE")
    return rows[0] if rows else None


async def _write_result_snapshot(
    connection: asyncpg.Connection,
    row: asyncpg.Record,
    job: GenerationJob,
    pending: dict[str, PendingInvocationRecord],
) -> None:
    provider, model = _job_provider_model(
        job,
        fallback_provider=str(row["provider"]),
        fallback_model=str(row["model"]),
    )
    await connection.execute(
        """
        UPDATE generations
        SET provider = $3,
            model = $4,
            status = $5,
            result_json = $6::jsonb
        WHERE id = $1 AND organization_id = $2
        """,
        row["id"],
        row["organization_id"],
        provider,
        model,
        job.status.casefold(),
        _json_dump(encode_result_snapshot(job, pending)),
    )


async def _lock_operation(
    connection: asyncpg.Connection,
    organization_id: str,
    operation_id: str,
) -> None:
    await connection.execute(
        "SELECT pg_advisory_xact_lock($1)",
        _lock_key(organization_id, operation_id),
    )


def _lock_key(organization_id: str, operation_id: str) -> int:
    digest = hashlib.sha256(
        f"node46-generation\x00{organization_id}\x00{operation_id}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _row_id(organization_id: str, operation_id: str) -> UUID:
    return uuid5(UUID(organization_id), f"node46-image-generation:{operation_id}")


def _job_provider_model(
    job: GenerationJob,
    *,
    fallback_provider: str,
    fallback_model: str,
) -> tuple[str, str]:
    for candidate in reversed(job.candidates):
        if candidate.provider and candidate.model:
            return candidate.provider, candidate.model
    return fallback_provider, fallback_model


def _job_from_result(value: Any) -> GenerationJob | None:
    snapshot = _optional_result_snapshot(value)
    return snapshot[0] if snapshot is not None else None


def _required_result_snapshot(
    value: Any,
) -> tuple[GenerationJob, dict[str, PendingInvocationRecord]]:
    snapshot = _optional_result_snapshot(value)
    if snapshot is None:
        raise GenerationRepositoryError("GENERATION_RESULT_SNAPSHOT_MISSING")
    return snapshot


def _optional_result_snapshot(
    value: Any,
) -> tuple[GenerationJob, dict[str, PendingInvocationRecord]] | None:
    payload = _json_object(value)
    if not payload:
        return None
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise GenerationRepositoryError("GENERATION_RESULT_SNAPSHOT_SCHEMA_UNSUPPORTED")
    return decode_result_snapshot(payload)


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GenerationRepositoryError("GENERATION_JSON_SNAPSHOT_INVALID")
    return value


def _json_dump(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _optional_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _asyncpg_dsn(database_dsn: str) -> str:
    if database_dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_dsn[len("postgresql+asyncpg://") :]
    if database_dsn.startswith("postgresql://"):
        return database_dsn
    raise ValueError("GENERATION_DATABASE_URL_MUST_USE_POSTGRESQL")
