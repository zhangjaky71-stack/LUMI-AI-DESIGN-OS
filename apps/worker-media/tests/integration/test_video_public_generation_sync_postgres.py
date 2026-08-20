from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from lumi_video_generation.model import ShotRuntime, ShotSpec, VideoJob, VideoTaskSpec
from lumi_video_generation.spec_codec import encode_spec
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


def _spec(*, task_id: UUID, operation_id: UUID) -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id=str(ORG),
        project_id=str(PROJECT),
        task_id=str(task_id),
        operation_id=str(operation_id),
        mode="TEXT_TO_VIDEO",
        prompt="A minimal public generation state sync fixture",
        duration_seconds=Decimal("4"),
        aspect_ratio="16:9",
        width=1280,
        height=720,
        fps=24,
        budget_limit_usd=Decimal("2.00"),
        code_git_sha="a" * 40,
        shots=(
            ShotSpec(
                shot_id="hero",
                duration_seconds=Decimal("4"),
                prompt="Slow neutral reveal",
            ),
        ),
        recipe_version="video-public-sync-v1",
    )


async def _acceptance() -> None:
    task_id = uuid4()
    operation_id = uuid4()
    generation_id = uuid4()
    paid_operation_id = uuid4()
    provider_request_id = f"provider-secret-{uuid4().hex}"
    spec = _spec(task_id=task_id, operation_id=operation_id)

    connection = await asyncpg.connect(_dsn())
    try:
        async with connection.transaction():
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
            await connection.execute(
                """
                INSERT INTO generations (
                    id, organization_id, project_id, task_id, agent_run_id,
                    operation_id, provider, model, capability, status,
                    request_json, result_json, created_at
                ) VALUES (
                    $1,$2,$3,$4,NULL,$5,
                    'model-gateway','routing-pending','video.generate','pending',
                    $6::jsonb,'{}'::jsonb,now()
                )
                """,
                generation_id,
                ORG,
                PROJECT,
                task_id,
                operation_id,
                json.dumps(encode_spec(spec), sort_keys=True, separators=(",", ":")),
            )
    finally:
        await connection.close()

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
                provider_request_id=provider_request_id,
            ),
        ),
        estimated_cost_usd=Decimal("1.25000000"),
    )
    repository = PostgresVideoRepository(os.environ["DATABASE_URL"])
    repository.save_spec(spec)
    repository.save(job)
    assert (
        await repository.flush(
            organization_id=str(ORG),
            operation_id=str(operation_id),
        )
        == job
    )

    connection = await asyncpg.connect(_dsn())
    try:
        row = await connection.fetchrow(
            """
            SELECT provider, model, capability, status, request_json, result_json
            FROM generations
            WHERE id=$1 AND organization_id=$2
            """,
            generation_id,
            ORG,
        )
    finally:
        await connection.close()

    assert row is not None
    assert row["provider"] == "openai"
    assert row["model"] == "sora-2"
    assert row["capability"] == "video.generate"
    assert row["status"] == "waiting_external"
    assert row["request_json"] == encode_spec(spec)
    assert row["result_json"]["schema_version"] == 1
    assert row["result_json"]["video_job_id"] == job.video_job_id
    assert row["result_json"]["status"] == "WAITING_EXTERNAL"
    assert row["result_json"]["shots"] == [
        {
            "shot_id": "hero",
            "status": "WAITING_EXTERNAL",
            "attempt_count": 1,
            "provider": "openai",
            "model": "sora-2",
            "artifact_version_id": None,
            "error_code": None,
        }
    ]
    assert provider_request_id not in json.dumps(row["result_json"], sort_keys=True)


def test_worker_syncs_public_video_generation_without_provider_request_leak() -> None:
    asyncio.run(_acceptance())
