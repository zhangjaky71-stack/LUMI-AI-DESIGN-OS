from __future__ import annotations

from uuid import uuid4

from lumi_domain.job_dispatch import (
    VIDEO_RENDER_QUEUE,
    VIDEO_RENDER_ROUTING_KEY,
    VIDEO_RENDER_TASK_NAME,
    JobDispatch,
    JobMessage,
)
from lumi_worker_media.job_dispatch_runtime import CeleryJobPublisher, MediaJobOutboxRecord


def _video_dispatch() -> JobDispatch:
    return JobDispatch(
        task_name=VIDEO_RENDER_TASK_NAME,
        queue=VIDEO_RENDER_QUEUE,
        message=JobMessage(
            job_id=uuid4(),
            organization_id=uuid4(),
            project_id=uuid4(),
            operation_id=uuid4(),
            trace_id="trace-video-dispatch",
        ),
    )


def test_video_outbox_record_accepts_canonical_video_route() -> None:
    dispatch = _video_dispatch()
    event_id = uuid4()
    record = MediaJobOutboxRecord(
        event_id=event_id,
        organization_id=dispatch.message.organization_id,
        aggregate_type="task",
        aggregate_id=dispatch.message.job_id,
        schema_version=1,
        payload=dispatch.as_outbox_payload(),
    )

    assert record.dispatch() == dispatch


def test_video_publisher_uses_canonical_queue_and_routing_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import lumi_worker_media.app as app

    captured: dict[str, object] = {}

    def fake_send_task(task_name: str, *args: object, **kwargs: object) -> object:
        captured["task_name"] = task_name
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(app.celery_app, "send_task", fake_send_task)
    dispatch = _video_dispatch()
    CeleryJobPublisher().publish(dispatch)

    assert captured["task_name"] == VIDEO_RENDER_TASK_NAME
    options = captured["kwargs"]
    assert isinstance(options, dict)
    assert options["queue"] == VIDEO_RENDER_QUEUE
    assert options["exchange"] == "lumi.jobs"
    assert options["routing_key"] == VIDEO_RENDER_ROUTING_KEY
    assert options["kwargs"] == {}
    assert options["args"] == [dispatch.message.as_dict()]


def test_video_dispatch_rejects_image_queue() -> None:
    dispatch = _video_dispatch()
    invalid = JobDispatch(
        task_name=dispatch.task_name,
        queue="lumi.media.image",
        message=dispatch.message,
    )
    record = MediaJobOutboxRecord(
        event_id=uuid4(),
        organization_id=dispatch.message.organization_id,
        aggregate_type="task",
        aggregate_id=dispatch.message.job_id,
        schema_version=1,
        payload=invalid.as_outbox_payload(),
    )

    try:
        record.dispatch()
    except ValueError as exc:
        assert str(exc) == "MEDIA_JOB_DISPATCH_QUEUE_MISMATCH"
    else:
        raise AssertionError("expected video queue mismatch to fail closed")
