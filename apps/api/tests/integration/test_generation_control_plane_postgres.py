from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from lumi_image_generation.model import ImageGenerationSpec, OutputRequirements
from lumi_image_generation.spec_codec import encode_spec
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.api.v1.contracts import GenerationCreate
from lumi_api.generations.errors import GenerationConflict
from lumi_api.generations.service import ImageGenerationControlPlane
from lumi_api.persistence.models import Generation, IdempotencyOperation, OutboxEvent, Task
from lumi_api.persistence.seed import ORG_ID, PROJECT_A_ID
from lumi_api.persistence.session import create_engine

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)


def _spec(*, task_id: str, operation_id: str) -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id=str(ORG_ID),
        project_id=str(PROJECT_A_ID),
        task_id=task_id,
        operation_id=operation_id,
        purpose="NODE-73.1 canonical dispatch integration",
        mode="TEXT_TO_IMAGE",
        prompt_compilation_ref="prompt://node-73-1/integration",
        objective="Create a deterministic integration fixture image.",
        content="A minimal neutral product scene.",
        visual_direction="minimal",
        aspect_ratio="1:1",
        target_width=1024,
        target_height=1024,
        variant_count=1,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile="DRAFT",
        budget_limit_usd=Decimal("1.00"),
        output_requirements=OutputRequirements(format="PNG"),
        code_git_sha="a" * 40,
    )


def _task(*, task_id: UUID) -> Task:
    return Task(
        id=task_id,
        organization_id=ORG_ID,
        project_id=PROJECT_A_ID,
        type="image.transform",
        status="pending",
        input_json={},
        output_json={},
        priority=100,
        attempt_count=0,
        max_attempts=4,
        budget_reserved=Decimal("0"),
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
                canonical_spec = encode_spec(spec)
                payload = GenerationCreate(
                    project_id=PROJECT_A_ID,
                    capability="image.generate",
                    request=canonical_spec,
                )
                service = ImageGenerationControlPlane(session)
                first = await service.create(
                    organization_id=ORG_ID,
                    payload=payload,
                    idempotency_key="node-73-1-integration-key-0001",
                    trace_id="node-73-1-integration",
                )
                await session.flush()

                replay = await service.create(
                    organization_id=ORG_ID,
                    payload=payload,
                    idempotency_key="node-73-1-integration-key-0001",
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
                        idempotency_key="node-73-1-integration-key-0002",
                        trace_id="alternate-key",
                    )

                # Prove the invariant is durable even if a future writer bypasses the
                # control-plane service and attempts a raw ORM insert.
                with pytest.raises(IntegrityError):
                    async with session.begin_nested():
                        session.add(
                            Generation(
                                organization_id=ORG_ID,
                                project_id=PROJECT_A_ID,
                                task_id=task_id,
                                operation_id=operation_id,
                                provider="model-gateway",
                                model="routing-pending",
                                capability="image.generate",
                                status="pending",
                                request_json=canonical_spec,
                                result_json={},
                            )
                        )
                        await session.flush()

                generation_count = await session.scalar(
                    select(func.count()).select_from(Generation).where(
                        Generation.organization_id == ORG_ID,
                        Generation.operation_id == operation_id,
                    )
                )
                task_count = await session.scalar(
                    select(func.count()).select_from(Task).where(Task.id == task_id)
                )
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
                                    "node-73-1-integration-key-0001",
                                    "node-73-1-integration-key-0002",
                                )
                            ),
                        )
                    )
                ).scalars().all()
                task = await session.get(Task, task_id)

                assert generation_count == 1
                assert task_count == 1
                assert len(outbox_rows) == 1
                assert len(idempotency_rows) == 1
                assert idempotency_rows[0].idempotency_key == "node-73-1-integration-key-0001"
                assert first.task_id == task_id
                assert task is not None
                assert task.organization_id == ORG_ID
                assert task.project_id == PROJECT_A_ID
                assert task.type == "image.transform"
                assert task.input_json["schema_version"] == 1
                assert task.input_json["job_kind"] == "image.transform"
                assert outbox_rows[0].payload_json["task_name"] == "lumi.jobs.image.transform"
                assert outbox_rows[0].payload_json["queue"] == "lumi.media.image"
                assert outbox_rows[0].payload_json["kwargs"] == {}
                assert outbox_rows[0].payload_json["args"] == [
                    {
                        "job_id": str(task_id),
                        "organization_id": str(ORG_ID),
                        "project_id": str(PROJECT_A_ID),
                        "operation_id": str(operation_id),
                        "trace_id": "node-73-1-integration",
                    }
                ]

                # Preserve compatibility for internal callers that already created the
                # canonical Task and pass its id explicitly.
                explicit_task_id = uuid4()
                explicit_operation_id = uuid4()
                session.add(_task(task_id=explicit_task_id))
                await session.flush()
                explicit_spec = _spec(
                    task_id=str(explicit_task_id),
                    operation_id=str(explicit_operation_id),
                )
                explicit = await service.create(
                    organization_id=ORG_ID,
                    payload=GenerationCreate(
                        project_id=PROJECT_A_ID,
                        task_id=explicit_task_id,
                        capability="image.generate",
                        request=encode_spec(explicit_spec),
                    ),
                    idempotency_key="node-73-1-explicit-task-0001",
                    trace_id="node-73-1-explicit-task",
                )
                await session.flush()
                assert explicit.task_id == explicit_task_id
                assert await session.get(Task, explicit_task_id) is not None
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


def test_generation_control_plane_transaction_and_replay() -> None:
    asyncio.run(_acceptance())
