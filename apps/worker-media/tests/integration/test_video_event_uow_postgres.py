from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from lumi_video_generation.model import ShotRuntime, ShotSpec, VideoJob, VideoTaskSpec
from lumi_worker_media.video_event_buffer import BufferedVideoEventSink
from lumi_worker_media.video_generation_repository import PostgresVideoRepository

pytestmark = pytest.mark.skipif(
    os.getenv("LUMI_DB_INTEGRATION") != "1",
    reason="set LUMI_DB_INTEGRATION=1 with migrated and seeded local PostgreSQL",
)

ORG = UUID("01900000-0000-7000-8000-000000000001")
PROJECT = UUID("01900000-0000-7000-8000-000000000006")


def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def _migration_dsn() -> str:
    return os.environ.get("MIGRATION_DATABASE_URL", os.environ["DATABASE_URL"]).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


async def _insert_task(task_id: UUID) -> None:
    connection = await asyncpg.connect(_migration_dsn())
    try:
        await connection.execute(
            """
            INSERT INTO tasks (
                id, organization_id, project_id, type, status,
                input_json, output_json, priority, attempt_count, max_attempts,
                budget_reserved, created_at, updated_at, version
            ) VALUES (
                $1,$2,$3,'video.render','pending',
                '{}'::jsonb,'{}'::jsonb,100,0,3,0,now(),now(),1
            )
            """,
            task_id,
            ORG,
            PROJECT,
        )
    finally:
        await connection.close()


def test_buffered_video_event_failure_rolls_back_snapshot_and_preserves_buffer() -> None:
    async def run() -> None:
        task_id = uuid4()
        operation_id = uuid4()
        await _insert_task(task_id)

        shot = ShotSpec(
            shot_id="hero",
            duration_seconds=Decimal("4"),
            prompt="Atomic video event UoW acceptance",
        )
        spec = VideoTaskSpec(
            organization_id=str(ORG),
            project_id=str(PROJECT),
            task_id=str(task_id),
            operation_id=str(operation_id),
            mode="TEXT_TO_VIDEO",
            prompt=shot.prompt,
            duration_seconds=Decimal("4"),
            aspect_ratio="16:9",
            width=1280,
            height=720,
            fps=24,
            budget_limit_usd=Decimal("5"),
            code_git_sha="a" * 40,
            shots=(shot,),
            recipe_version="video-event-uow-postgres-v1",
        )
        paid_operation_id = uuid4()
        job = VideoJob(
            video_job_id=f"video-job:{uuid4().hex}",
            organization_id=str(ORG),
            operation_id=str(operation_id),
            semantic_hash=spec.semantic_hash,
            storyboard_hash="b" * 64,
            status="WAITING_EXTERNAL",
            shots=(
                ShotRuntime(
                    shot_id="hero",
                    ordinal=1,
                    paid_operation_id=str(paid_operation_id),
                    status="WAITING_EXTERNAL",
                    attempt_count=1,
                    provider="openai",
                    model="sora-2",
                    provider_request_id=f"video_uow_{paid_operation_id.hex}",
                ),
            ),
        )

        repository = PostgresVideoRepository(os.environ["DATABASE_URL"])
        repository.save_spec(spec)
        repository.save(job)

        # Use a valid UUID that is deliberately absent from organizations. The event
        # insert is the final write inside repository.flush(), so its FK rejection
        # proves earlier snapshot writes are rolled back by the same transaction.
        event_sink = BufferedVideoEventSink(os.environ["DATABASE_URL"])
        await event_sink.emit(
            "video_generation.external_wait",
            organization_id=str(uuid4()),
            video_job_id=job.video_job_id,
            payload={"shot_id": "hero", "status": "WAITING_EXTERNAL"},
        )
        assert event_sink.pending_count == 1

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await repository.flush(
                organization_id=str(ORG),
                operation_id=str(operation_id),
                event_sink=event_sink,
            )

        assert event_sink.pending_count == 1
        connection = await asyncpg.connect(_dsn())
        try:
            snapshot_count = await connection.fetchval(
                """
                SELECT count(*)
                FROM video_generation_jobs
                WHERE organization_id=$1 AND operation_id=$2
                """,
                ORG,
                operation_id,
            )
            event_count = await connection.fetchval(
                """
                SELECT count(*)
                FROM outbox_events
                WHERE aggregate_type='video_generation'
                  AND payload_json ->> 'video_job_id' = $1
                """,
                job.video_job_id,
            )
        finally:
            await connection.close()

        assert snapshot_count == 0
        assert event_count == 0

    asyncio.run(run())
