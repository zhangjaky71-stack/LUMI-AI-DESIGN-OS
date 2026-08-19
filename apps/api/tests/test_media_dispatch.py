from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.media_dispatch import (
    IMAGE_TRANSFORM_QUEUE,
    IMAGE_TRANSFORM_TASK_NAME,
    MEDIA_DISPATCH_EVENT_NAME,
    CanonicalMediaDispatch,
    build_image_transform_dispatch,
    publish_media_outbox_event,
    stage_image_transform_dispatch,
)
from lumi_api.persistence.models import Generation, OutboxEvent, Task


def _fixture_models(
    monkeypatch: pytest.MonkeyPatch,
    *,
    task_hash: str = "semantic-1",
    generation_hash: str = "semantic-1",
) -> tuple[Task, Generation, dict[str, UUID]]:
    ids = {
        "task": uuid4(),
        "organization": uuid4(),
        "project": uuid4(),
        "operation": uuid4(),
    }
    task_spec_payload: dict[str, Any] = {"fixture": "task"}
    generation_spec_payload: dict[str, Any] = {"fixture": "generation"}

    def fake_decode_spec(payload: dict[str, Any]) -> SimpleNamespace:
        semantic_hash = task_hash if payload is task_spec_payload else generation_hash
        return SimpleNamespace(
            semantic_hash=semantic_hash,
            organization_id=str(ids["organization"]),
            project_id=str(ids["project"]),
            task_id=str(ids["task"]),
            operation_id=str(ids["operation"]),
        )

    monkeypatch.setattr("lumi_api.media_dispatch.decode_spec", fake_decode_spec)
    task = cast(
        Task,
        SimpleNamespace(
            id=ids["task"],
            organization_id=ids["organization"],
            project_id=ids["project"],
            type="image.transform",
            input_json={
                "schema_version": 1,
                "job_kind": "image.transform",
                "image_generation_spec": task_spec_payload,
            },
        ),
    )
    generation = cast(
        Generation,
        SimpleNamespace(
            task_id=ids["task"],
            organization_id=ids["organization"],
            project_id=ids["project"],
            operation_id=ids["operation"],
            request_json=generation_spec_payload,
        ),
    )
    return task, generation, ids


def test_build_dispatch_matches_worker_entrypoint_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    task, generation, ids = _fixture_models(monkeypatch)

    dispatch = build_image_transform_dispatch(
        task=task,
        generation=generation,
        trace_id="trace-73-1",
    )
    payload = dispatch.as_outbox_payload()

    assert dispatch.task_name == IMAGE_TRANSFORM_TASK_NAME
    assert dispatch.queue == IMAGE_TRANSFORM_QUEUE
    assert payload["task_name"] == "lumi.jobs.image.transform"
    assert payload["queue"] == "lumi.media.image"
    assert payload["kwargs"] == {}
    assert payload["args"] == [
        {
            "job_id": str(ids["task"]),
            "organization_id": str(ids["organization"]),
            "project_id": str(ids["project"]),
            "operation_id": str(ids["operation"]),
            "trace_id": "trace-73-1",
        }
    ]


def test_build_dispatch_fails_closed_on_generation_spec_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, generation, _ = _fixture_models(
        monkeypatch,
        task_hash="task-hash",
        generation_hash="generation-hash",
    )

    with pytest.raises(ValueError, match="MEDIA_DISPATCH_GENERATION_SPEC_MISMATCH"):
        build_image_transform_dispatch(task=task, generation=generation, trace_id=None)


def test_build_dispatch_fails_closed_on_cross_tenant_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, generation, _ = _fixture_models(monkeypatch)
    generation.organization_id = uuid4()

    with pytest.raises(ValueError, match="MEDIA_DISPATCH_GENERATION_ORGANIZATION_MISMATCH"):
        build_image_transform_dispatch(task=task, generation=generation, trace_id=None)


def test_outbox_decoder_rejects_extra_fields_and_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, generation, _ = _fixture_models(monkeypatch)
    payload = build_image_transform_dispatch(
        task=task,
        generation=generation,
        trace_id=None,
    ).as_outbox_payload()

    with pytest.raises(ValueError, match="MEDIA_DISPATCH_UNKNOWN_FIELDS"):
        CanonicalMediaDispatch.from_outbox_payload({**payload, "prompt": "forbidden"})

    payload_with_kwargs = {**payload, "kwargs": {"prompt": "forbidden"}}
    with pytest.raises(ValueError, match="MEDIA_DISPATCH_KWARGS_FORBIDDEN"):
        CanonicalMediaDispatch.from_outbox_payload(payload_with_kwargs)


def test_stage_dispatch_only_adds_outbox_inside_callers_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, generation, ids = _fixture_models(monkeypatch)

    class FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []

        def add(self, value: object) -> None:
            self.added.append(value)

    fake_session = FakeSession()
    event = stage_image_transform_dispatch(
        cast(AsyncSession, fake_session),
        task=task,
        generation=generation,
        trace_id="trace-outbox",
    )

    assert fake_session.added == [event]
    assert event.event_name == MEDIA_DISPATCH_EVENT_NAME
    assert event.aggregate_type == "task"
    assert event.aggregate_id == ids["task"]
    assert event.organization_id == ids["organization"]
    assert event.published_at is None
    assert event.publish_attempts == 0


def test_publish_success_sets_timestamp_only_after_broker_accepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, generation, ids = _fixture_models(monkeypatch)
    dispatch = build_image_transform_dispatch(
        task=task,
        generation=generation,
        trace_id="trace-publish",
    )
    event = cast(
        OutboxEvent,
        SimpleNamespace(
            published_at=None,
            publish_attempts=0,
            event_name=MEDIA_DISPATCH_EVENT_NAME,
            aggregate_type="task",
            aggregate_id=ids["task"],
            organization_id=ids["organization"],
            schema_version=1,
            payload_json=dispatch.as_outbox_payload(),
        ),
    )

    class Broker:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def publish_task(self, **kwargs: object) -> None:
            self.calls.append(dict(kwargs))

    broker = Broker()
    timestamp = datetime(2026, 8, 19, 6, 30, tzinfo=UTC)
    published = asyncio.run(
        publish_media_outbox_event(
            event=event,
            broker=broker,
            published_at=timestamp,
        )
    )

    assert published is True
    assert event.publish_attempts == 1
    assert event.published_at == timestamp
    assert broker.calls == [
        {
            "task_name": "lumi.jobs.image.transform",
            "queue": "lumi.media.image",
            "args": [dispatch.message.as_dict()],
            "kwargs": {},
        }
    ]


def test_publish_failure_increments_attempt_without_marking_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, generation, ids = _fixture_models(monkeypatch)
    dispatch = build_image_transform_dispatch(
        task=task,
        generation=generation,
        trace_id=None,
    )
    event = cast(
        OutboxEvent,
        SimpleNamespace(
            published_at=None,
            publish_attempts=0,
            event_name=MEDIA_DISPATCH_EVENT_NAME,
            aggregate_type="task",
            aggregate_id=ids["task"],
            organization_id=ids["organization"],
            schema_version=1,
            payload_json=dispatch.as_outbox_payload(),
        ),
    )

    class FailingBroker:
        async def publish_task(self, **_: object) -> None:
            raise RuntimeError("broker unavailable")

    with pytest.raises(RuntimeError, match="broker unavailable"):
        asyncio.run(publish_media_outbox_event(event=event, broker=FailingBroker()))

    assert event.publish_attempts == 1
    assert event.published_at is None
