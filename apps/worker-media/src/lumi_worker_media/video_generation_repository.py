from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid5

import asyncpg
from lumi_video_generation.model import ProviderJobRecord, VideoJob, VideoTaskSpec
from lumi_video_generation.repository import InMemoryVideoRepository, VideoOperationConflict

from .video_generation_codec import (
    decode_provider_record,
    decode_video_job,
    decode_video_task_spec,
    encode_provider_record,
    encode_video_job,
    encode_video_task_spec,
)


class PostgresVideoRepository(InMemoryVideoRepository):
    """Invocation-local NODE-48 repository with durable PostgreSQL load/flush.

    The domain pipeline intentionally retains its synchronous repository protocol.
    Hosted execution hydrates this UoW before one start/resume step and flushes the
    complete recovery snapshot afterwards. Provider paid-operation crash safety is
    separately enforced by NODE-20 in Model Gateway; this repository never owns a
    second paid-side-effect ledger.
    """

    def __init__(self, database_dsn: str) -> None:
        super().__init__()
        self.dsn = _asyncpg_dsn(database_dsn)

    async def load(self, *, organization_id: str, operation_id: str) -> VideoJob | None:
        connection = await asyncpg.connect(self.dsn)
        try:
            rows = await connection.fetch(
                """
                SELECT id, organization_id, project_id, task_id, operation_id,
                       semantic_hash, storyboard_hash, status,
                       spec_snapshot, job_snapshot
                FROM video_generation_jobs
                WHERE organization_id=$1 AND operation_id=$2
                ORDER BY created_at, id
                LIMIT 2
                """,
                UUID(organization_id),
                UUID(operation_id),
            )
            if len(rows) > 1:
                raise VideoOperationConflict("VIDEO_OPERATION_DUPLICATE")
            if not rows:
                return None
            row = rows[0]
            spec = decode_video_task_spec(_json_object(row["spec_snapshot"]))
            job = decode_video_job(_json_object(row["job_snapshot"]))
            _assert_row_identity(row, spec=spec, job=job)
            self.save_spec(spec)
            self.save(job)

            provider_rows = await connection.fetch(
                """
                SELECT active, result_snapshot
                FROM video_provider_jobs
                WHERE organization_id=$1 AND video_job_id=$2
                ORDER BY created_at, id
                """,
                UUID(organization_id),
                row["id"],
            )
            for provider_row in provider_rows:
                record = decode_provider_record(_json_object(provider_row["result_snapshot"]))
                _assert_provider_identity(record, spec=spec, job=job)
                if bool(provider_row["active"]):
                    self.save_provider_job(record)
                else:
                    key = (
                        record.organization_id,
                        record.video_job_id,
                        record.shot_id,
                        record.paid_operation_id,
                    )
                    existing = self.terminal_provider_jobs.get(key)
                    if existing is not None and existing != record:
                        raise VideoOperationConflict("VIDEO_PROVIDER_TERMINAL_IDENTITY_CONFLICT")
                    self.terminal_provider_jobs[key] = record
            return job
        finally:
            await connection.close()

    async def flush(self, *, organization_id: str, operation_id: str) -> VideoJob:
        spec = self.get_spec(organization_id, operation_id)
        job = self.get_by_operation(organization_id, operation_id)
        if spec is None or job is None:
            raise RuntimeError("VIDEO_RUNTIME_SNAPSHOT_INCOMPLETE")
        if spec.semantic_hash != job.semantic_hash:
            raise VideoOperationConflict("VIDEO_OPERATION_SEMANTIC_CONFLICT")
        row_id = _row_id(organization_id, operation_id)
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock($1)",
                    _lock_key(organization_id, operation_id),
                )
                task_identity = await connection.fetchrow(
                    """
                    SELECT organization_id, project_id, type
                    FROM tasks
                    WHERE id=$1
                    """,
                    UUID(spec.task_id),
                )
                if task_identity is None:
                    raise RuntimeError("VIDEO_TASK_NOT_FOUND")
                if (
                    task_identity["organization_id"] != UUID(spec.organization_id)
                    or task_identity["project_id"] != UUID(spec.project_id)
                    or task_identity["type"] != "video.render"
                ):
                    raise RuntimeError("VIDEO_TASK_IDENTITY_MISMATCH")

                await connection.execute(
                    """
                    INSERT INTO video_generation_jobs (
                        id, organization_id, project_id, task_id, operation_id,
                        semantic_hash, storyboard_hash, status,
                        estimated_cost_usd, actual_cost_usd,
                        spec_snapshot, job_snapshot, final_artifact_version_id,
                        error_code, created_at, updated_at, version
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                        $11::jsonb,$12::jsonb,$13,$14,now(),now(),1
                    )
                    ON CONFLICT (organization_id, operation_id) DO UPDATE SET
                        semantic_hash=EXCLUDED.semantic_hash,
                        storyboard_hash=EXCLUDED.storyboard_hash,
                        status=EXCLUDED.status,
                        estimated_cost_usd=EXCLUDED.estimated_cost_usd,
                        actual_cost_usd=EXCLUDED.actual_cost_usd,
                        spec_snapshot=EXCLUDED.spec_snapshot,
                        job_snapshot=EXCLUDED.job_snapshot,
                        final_artifact_version_id=EXCLUDED.final_artifact_version_id,
                        error_code=EXCLUDED.error_code,
                        updated_at=now(),
                        version=video_generation_jobs.version+1
                    """,
                    row_id,
                    UUID(spec.organization_id),
                    UUID(spec.project_id),
                    UUID(spec.task_id),
                    UUID(spec.operation_id),
                    spec.semantic_hash,
                    job.storyboard_hash,
                    job.status,
                    job.estimated_cost_usd,
                    job.actual_cost_usd,
                    _json(encode_video_task_spec(spec)),
                    _json(encode_video_job(job)),
                    _optional_uuid(job.final_artifact_version_id),
                    job.error_code,
                )
                persisted = await connection.fetchrow(
                    """
                    SELECT id, organization_id, project_id, task_id, semantic_hash
                    FROM video_generation_jobs
                    WHERE organization_id=$1 AND operation_id=$2
                    FOR UPDATE
                    """,
                    UUID(organization_id),
                    UUID(operation_id),
                )
                if persisted is None or persisted["id"] != row_id:
                    raise RuntimeError("VIDEO_RUNTIME_ROW_IDENTITY_CONFLICT")
                if (
                    persisted["organization_id"] != UUID(spec.organization_id)
                    or persisted["project_id"] != UUID(spec.project_id)
                    or persisted["task_id"] != UUID(spec.task_id)
                    or persisted["semantic_hash"] != spec.semantic_hash
                ):
                    raise RuntimeError("VIDEO_RUNTIME_ROW_SCOPE_CONFLICT")

                await connection.execute(
                    "UPDATE video_provider_jobs SET active=false, updated_at=now(), version=version+1 "
                    "WHERE organization_id=$1 AND video_job_id=$2 AND active",
                    UUID(organization_id),
                    row_id,
                )
                terminal = [
                    record
                    for key, record in self.terminal_provider_jobs.items()
                    if key[0] == organization_id and key[1] == job.video_job_id
                ]
                active = [
                    record
                    for key, record in self.provider_jobs.items()
                    if key[0] == organization_id and key[1] == job.video_job_id
                ]
                for record in terminal:
                    await _upsert_provider(connection, row_id=row_id, record=record, active=False)
                for record in active:
                    await _upsert_provider(connection, row_id=row_id, record=record, active=True)
            return job
        finally:
            await connection.close()


async def _upsert_provider(
    connection: asyncpg.Connection,
    *,
    row_id: UUID,
    record: ProviderJobRecord,
    active: bool,
) -> None:
    provider_row_id = uuid5(
        row_id,
        f"provider:{record.shot_id}:{record.paid_operation_id}",
    )
    await connection.execute(
        """
        INSERT INTO video_provider_jobs (
            id, organization_id, video_job_id, shot_id, paid_operation_id,
            request_hash, provider, model, provider_request_id, status,
            active, result_snapshot, attempt_ordinal, created_at, updated_at, version
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,0,now(),now(),1
        )
        ON CONFLICT (video_job_id, shot_id, paid_operation_id) DO UPDATE SET
            request_hash=EXCLUDED.request_hash,
            provider=EXCLUDED.provider,
            model=EXCLUDED.model,
            provider_request_id=EXCLUDED.provider_request_id,
            status=EXCLUDED.status,
            active=EXCLUDED.active,
            result_snapshot=EXCLUDED.result_snapshot,
            updated_at=now(),
            version=video_provider_jobs.version+1
        """,
        provider_row_id,
        UUID(record.organization_id),
        row_id,
        record.shot_id,
        UUID(record.paid_operation_id),
        record.request_hash,
        record.result.provider,
        record.result.model,
        record.result.provider_request_id,
        record.result.status,
        active,
        _json(encode_provider_record(record)),
    )


def _assert_row_identity(row: asyncpg.Record, *, spec: VideoTaskSpec, job: VideoJob) -> None:
    if UUID(spec.organization_id) != row["organization_id"]:
        raise RuntimeError("VIDEO_RUNTIME_ORGANIZATION_MISMATCH")
    if UUID(spec.project_id) != row["project_id"]:
        raise RuntimeError("VIDEO_RUNTIME_PROJECT_MISMATCH")
    if UUID(spec.task_id) != row["task_id"]:
        raise RuntimeError("VIDEO_RUNTIME_TASK_MISMATCH")
    if UUID(spec.operation_id) != row["operation_id"] or job.operation_id != spec.operation_id:
        raise RuntimeError("VIDEO_RUNTIME_OPERATION_MISMATCH")
    if spec.semantic_hash != row["semantic_hash"] or job.semantic_hash != spec.semantic_hash:
        raise VideoOperationConflict("VIDEO_OPERATION_SEMANTIC_CONFLICT")
    if job.storyboard_hash != row["storyboard_hash"] or job.status != row["status"]:
        raise RuntimeError("VIDEO_RUNTIME_JOB_SNAPSHOT_MISMATCH")


def _assert_provider_identity(
    record: ProviderJobRecord,
    *,
    spec: VideoTaskSpec,
    job: VideoJob,
) -> None:
    if record.organization_id != spec.organization_id or record.video_job_id != job.video_job_id:
        raise RuntimeError("VIDEO_PROVIDER_SCOPE_MISMATCH")
    if not any(item.shot_id == record.shot_id for item in job.shots):
        raise RuntimeError("VIDEO_PROVIDER_SHOT_UNKNOWN")


def _row_id(organization_id: str, operation_id: str) -> UUID:
    return uuid5(UUID(organization_id), f"node48-video-generation:{operation_id}")


def _lock_key(organization_id: str, operation_id: str) -> int:
    digest = hashlib.sha256(
        f"node48-video-generation\x00{organization_id}\x00{operation_id}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError("VIDEO_RUNTIME_JSON_OBJECT_REQUIRED")
    return dict(value)


def _optional_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    return UUID(value)


def _asyncpg_dsn(database_dsn: str) -> str:
    if database_dsn.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_dsn[len("postgresql+asyncpg://") :]
    if database_dsn.startswith("postgresql://"):
        return database_dsn
    raise ValueError("VIDEO_DATABASE_URL_MUST_USE_POSTGRESQL")
