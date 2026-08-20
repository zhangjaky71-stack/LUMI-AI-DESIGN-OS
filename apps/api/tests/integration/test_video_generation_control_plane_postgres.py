from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from lumi_video_generation.model import ShotSpec, VideoTaskSpec
from lumi_video_generation.spec_codec import encode_spec
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.api.v1.contracts import GenerationCreate
from lumi_api.generations.errors import GenerationConflict
from lumi_api.generations.video_service import VideoGenerationControlPlane
from lumi_api.persistence.models import Generation, IdempotencyOperation, OutboxEvent, Task
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID
from lumi_api.persistence.session import create_engine

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)


def _spec(*, task_id: str, operation_id: str) -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id=str(ORG_ID),
        project_id=str(PROJECT_A_ID),
        task_id=task_id,
        operation_id=operation_id,
        mode="TEXT_TO_VIDEO",
        prompt="A minimal studio reveal",
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
                prompt="Slow neutral product reveal",
            ),
        ),
        recipe_version="video-control-plane-v1",
    )


async def _acceptance() -> None:
    engine = create_engine()
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            session = AsyncSession(bind=connection, expire_on_commit=False)
            try:
                task_id = uuid4()
                operation_id = uuid4()
                spec = _spec(task_id=str(task_id), operation_id=str(operation_id))
                payload = GenerationCreate(
                    project_id=PROJECT_A_ID,
                    capability="video.generate",
                    request=encode_spec(spec),
                )
                service = VideoGenerationControlPlane(session)
                first = await service.create(
                    organization_id=ORG_ID,
                    payload=payload,
                    idempotency_key="video-control-plane-postgres-0001",
                    trace_id="video-control-plane-trace",
                )
                await session.flush()

                replay = await service.create(
                    organization_id=ORG_ID,
                    payload=payload,
                    idempotency_key="video-control-plane-postgres-0001",
                    trace_id="different-transient-trace",
                )
                await session.flush()
                assert replay.id == first.id

                with pytest.raises(
                    GenerationConflict,
                    match="GENERATION_OPERATION_ALREADY_EXISTS",
                ):
                    await service.create(
                        organization_id=ORG_ID,
                        payload=payload,
                        idempotency_key="video-control-plane-postgres-0002",
                        trace_id="alternate-key",
                    )

                generation_count = await session.scalar(
                    select(func.count()).select_from(Generation).where(
                        Generation.organization_id == ORG_ID,
                        Generation.operation_id == operation_id,
                    )
                )
                task = await session.get(Task, task_id)
                outbox_rows = (
                    await session.execute(
                        select(OutboxEvent).where(
                            OutboxEvent.organization_id == ORG_ID,
                            OutboxEvent.event_name == "job.dispatch.requested",
                            OutboxEvent.aggregate_id == task_id,
                        )
                    )
                ).scalars().all()
                idempotency_rows = (
                    await session.execute(
                        select(IdempotencyOperation).where(
                            IdempotencyOperation.organization_id == ORG_ID,
                            IdempotencyOperation.operation_type == "api.v1.generation.create",
                            IdempotencyOperation.idempotency_key.in_(
                                (
                                    "video-control-plane-postgres-0001",
                                    "video-control-plane-postgres-0002",
                                )
                            ),
                        )
                    )
                ).scalars().all()

                assert generation_count == 1
                assert task is not None
                assert task.type == "video.render"
                assert task.status == "pending"
                assert task.input_json["schema_version"] == 1
                assert task.input_json["job_kind"] == "video.render"
                assert task.input_json["video_generation_spec"] == encode_spec(spec)
                assert first.capability == "video.generate"
                assert first.provider == "model-gateway"
                assert first.model == "routing-pending"
                assert first.status == "pending"
                assert first.request_json == encode_spec(spec)

                assert len(outbox_rows) == 1
                assert outbox_rows[0].payload_json["task_name"] == "lumi.jobs.video.render"
                assert outbox_rows[0].payload_json["queue"] == "lumi.media.video"
                assert outbox_rows[0].payload_json["kwargs"] == {}
                assert outbox_rows[0].payload_json["args"] == [
                    {
                        "job_id": str(task_id),
                        "organization_id": str(ORG_ID),
                        "project_id": str(PROJECT_A_ID),
                        "operation_id": str(operation_id),
                        "trace_id": "video-control-plane-trace",
                    }
                ]

                assert len(idempotency_rows) == 1
                assert idempotency_rows[0].idempotency_key == "video-control-plane-postgres-0001"
                assert idempotency_rows[0].status == "succeeded"
                assert idempotency_rows[0].business_scope_id == task_id
                assert idempotency_rows[0].result_json == {"generation_id": str(first.id)}
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_video_generation_control_plane_transaction_and_replay() -> None:
    asyncio.run(_acceptance())
