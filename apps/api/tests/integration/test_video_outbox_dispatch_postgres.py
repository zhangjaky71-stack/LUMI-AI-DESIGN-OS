from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from lumi_video_generation.model import ShotSpec, VideoTaskSpec
from lumi_video_generation.spec_codec import encode_spec
from lumi_worker_media.job_dispatch_runtime import MediaJobOutboxDispatcher

from lumi_api.api.v1.contracts import GenerationCreate
from lumi_api.generations.video_service import VideoGenerationControlPlane
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID
from lumi_api.persistence.session import create_engine, create_session_factory

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)


def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def _spec(*, task_id: UUID, operation_id: UUID) -> VideoTaskSpec:
    return VideoTaskSpec(
        organization_id=str(ORG_ID),
        project_id=str(PROJECT_A_ID),
        task_id=str(task_id),
        operation_id=str(operation_id),
        mode="TEXT_TO_VIDEO",
        prompt="A canonical producer to outbox dispatcher acceptance fixture",
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
        recipe_version="video-outbox-dispatch-v1",
    )


class _CapturePublisher:
    def __init__(self) -> None:
        self.dispatches: list[object] = []

    def publish(self, dispatch: object) -> None:
        self.dispatches.append(dispatch)


async def _acceptance() -> None:
    task_id = uuid4()
    operation_id = uuid4()
    spec = _spec(task_id=task_id, operation_id=operation_id)
    payload = GenerationCreate(
        project_id=PROJECT_A_ID,
        capability="video.generate",
        request=encode_spec(spec),
    )

    engine = create_engine()
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session, session.begin():
            await VideoGenerationControlPlane(session).create(
                organization_id=ORG_ID,
                payload=payload,
                idempotency_key=f"video-outbox-dispatch:{operation_id}",
                trace_id="video-outbox-dispatch-postgres",
            )
    finally:
        await engine.dispose()

    publisher = _CapturePublisher()
    dispatcher = MediaJobOutboxDispatcher(_dsn(), publisher)
    published = await dispatcher.dispatch_batch(limit=1000)
    assert published >= 1

    matched = []
    for item in publisher.dispatches:
        task_name = getattr(item, "task_name", None)
        queue = getattr(item, "queue", None)
        message = getattr(item, "message", None)
        if getattr(message, "job_id", None) == task_id:
            matched.append((task_name, queue, message))
    assert len(matched) == 1
    task_name, queue, message = matched[0]
    assert task_name == "lumi.jobs.video.render"
    assert queue == "lumi.media.video"
    assert message.organization_id == ORG_ID
    assert message.project_id == PROJECT_A_ID
    assert message.operation_id == operation_id
    assert message.trace_id == "video-outbox-dispatch-postgres"

    connection = await asyncpg.connect(_dsn())
    try:
        row = await connection.fetchrow(
            """
            SELECT published_at, publish_attempts, payload_json
            FROM outbox_events
            WHERE organization_id=$1
              AND aggregate_type='task'
              AND aggregate_id=$2
              AND event_name='job.dispatch.requested'
            """,
            ORG_ID,
            task_id,
        )
    finally:
        await connection.close()
    assert row is not None
    assert row["published_at"] is not None
    assert row["publish_attempts"] == 1
    assert row["payload_json"]["task_name"] == "lumi.jobs.video.render"
    assert row["payload_json"]["queue"] == "lumi.media.video"


def test_video_control_plane_outbox_reaches_canonical_dispatcher() -> None:
    asyncio.run(_acceptance())
