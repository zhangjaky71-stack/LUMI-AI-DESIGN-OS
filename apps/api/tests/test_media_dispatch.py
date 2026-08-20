from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import lumi_api.media_dispatch as media_dispatch
from lumi_api.media_dispatch import (
    IMAGE_TRANSFORM_QUEUE,
    IMAGE_TRANSFORM_TASK_NAME,
    MEDIA_DISPATCH_EVENT_NAME,
    VIDEO_RENDER_QUEUE,
    VIDEO_RENDER_TASK_NAME,
    CanonicalMediaDispatch,
    build_image_transform_dispatch,
    build_video_render_dispatch,
    stage_image_transform_dispatch,
    stage_video_render_dispatch,
)
from lumi_api.persistence.models import Generation, Task


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

    monkeypatch.setattr("lumi_api.media_dispatch.decode_image_spec", fake_decode_spec)
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


def _video_task(monkeypatch: pytest.MonkeyPatch) -> tuple[Task, dict[str, UUID]]:
    ids = {
        "task": uuid4(),
        "organization": uuid4(),
        "project": uuid4(),
        "operation": uuid4(),
    }
    payload: dict[str, Any] = {"fixture": "video"}

    def fake_decode_video_spec(value: dict[str, Any]) -> SimpleNamespace:
        assert value is payload
        return SimpleNamespace(
            organization_id=str(ids["organization"]),
            project_id=str(ids["project"]),
            task_id=str(ids["task"]),
            operation_id=str(ids["operation"]),
        )

    monkeypatch.setattr("lumi_api.media_dispatch.decode_video_spec", fake_decode_video_spec)
    task = cast(
        Task,
        SimpleNamespace(
            id=ids["task"],
            organization_id=ids["organization"],
            project_id=ids["project"],
            type="video.render",
            input_json={
                "schema_version": 1,
                "job_kind": "video.render",
                "video_generation_spec": payload,
            },
        ),
    )
    return task, ids


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


def test_build_video_dispatch_matches_worker_entrypoint_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, ids = _video_task(monkeypatch)
    dispatch = build_video_render_dispatch(task=task, trace_id="trace-video-1")
    payload = dispatch.as_outbox_payload()

    assert dispatch.task_name == VIDEO_RENDER_TASK_NAME
    assert dispatch.queue == VIDEO_RENDER_QUEUE
    assert payload["task_name"] == "lumi.jobs.video.render"
    assert payload["queue"] == "lumi.media.video"
    assert payload["kwargs"] == {}
    assert payload["args"] == [
        {
            "job_id": str(ids["task"]),
            "organization_id": str(ids["organization"]),
            "project_id": str(ids["project"]),
            "operation_id": str(ids["operation"]),
            "trace_id": "trace-video-1",
        }
    ]


def test_build_video_dispatch_fails_closed_on_cross_tenant_spec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, ids = _video_task(monkeypatch)
    task.organization_id = uuid4()
    with pytest.raises(ValueError, match="VIDEO_DISPATCH_SPEC_ORGANIZATION_MISMATCH"):
        build_video_render_dispatch(task=task, trace_id=None)
    assert task.organization_id != ids["organization"]


def test_outbox_decoder_rejects_extra_fields_and_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, generation, _ = _fixture_models(monkeypatch)
    payload = build_image_transform_dispatch(
        task=task,
        generation=generation,
        trace_id=None,
    ).as_outbox_payload()

    with pytest.raises(ValueError, match="JOB_DISPATCH_UNKNOWN_FIELDS"):
        CanonicalMediaDispatch.from_outbox_payload({**payload, "prompt": "forbidden"})

    payload_with_kwargs = {**payload, "kwargs": {"prompt": "forbidden"}}
    with pytest.raises(ValueError, match="JOB_DISPATCH_KWARGS_FORBIDDEN"):
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


def test_stage_video_dispatch_is_deterministic_and_namespaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, ids = _video_task(monkeypatch)

    class FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []

        def add(self, value: object) -> None:
            self.added.append(value)

    first_session = FakeSession()
    second_session = FakeSession()
    first = stage_video_render_dispatch(
        cast(AsyncSession, first_session),
        task=task,
        trace_id="trace-video",
    )
    second = stage_video_render_dispatch(
        cast(AsyncSession, second_session),
        task=task,
        trace_id="trace-video",
    )

    assert first.id == second.id
    assert first.aggregate_id == ids["task"]
    assert first.organization_id == ids["organization"]
    assert first.payload_json["task_name"] == VIDEO_RENDER_TASK_NAME
    assert first.payload_json["queue"] == VIDEO_RENDER_QUEUE
    assert first_session.added == [first]
    assert second_session.added == [second]


def test_api_media_dispatch_has_no_direct_broker_publisher() -> None:
    assert not hasattr(media_dispatch, "MediaTaskBroker")
    assert not hasattr(media_dispatch, "publish_media_outbox_event")
