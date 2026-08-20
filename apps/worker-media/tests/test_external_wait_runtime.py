from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

from lumi_domain.job_dispatch import (
    JOB_DISPATCH_EVENT_NAME,
    VIDEO_RENDER_QUEUE,
    VIDEO_RENDER_TASK_NAME,
    JobDispatch,
    JobMessage,
)
from lumi_worker_media.external_wait_runtime import MediaExternalWaitWakeScheduler
from lumi_worker_media.job_runtime import ExternalWait, TaskJobStore, execute_job
from lumi_worker_media.queue_contracts import JobState


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeWakeConnection:
    def __init__(self, *, task: dict[str, object], dispatch: JobDispatch) -> None:
        self.task = task
        self.dispatch = dispatch
        self.due = True
        self.inserted_event_ids: list[UUID] = []
        self.closed = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        assert "status = 'waiting_external'" in query
        assert "FOR UPDATE SKIP LOCKED" in query
        assert args == (100,)
        return [self.task] if self.due else []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        assert "FROM outbox_events" in query
        assert args[2] == JOB_DISPATCH_EVENT_NAME
        return {
            "id": uuid4(),
            "schema_version": 1,
            "payload_json": self.dispatch.as_outbox_payload(),
        }

    async def execute(self, query: str, *args: object) -> str:
        if "INSERT INTO outbox_events" in query:
            self.inserted_event_ids.append(cast(UUID, args[0]))
            return "INSERT 0 1"
        if "UPDATE tasks" in query:
            self.due = False
            self.task["state_version"] = args[3]
            return "UPDATE 1"
        raise AssertionError(query)

    async def close(self) -> None:
        self.closed = True


class FakeJobStore:
    def __init__(self) -> None:
        self.waits: list[ExternalWait] = []
        self.succeeded = False
        self.failed = False

    async def cancellation_requested(self, message: JobMessage) -> bool:
        del message
        return False

    async def claim(self, message: JobMessage) -> int:
        del message
        return 1

    async def wait_external(self, message: JobMessage, wait: ExternalWait) -> None:
        del message
        self.waits.append(wait)

    async def succeed(self, message: JobMessage, output: dict[str, Any]) -> None:
        del message, output
        self.succeeded = True

    async def cancel(self, message: JobMessage) -> None:
        del message
        raise AssertionError("cancel must not run")

    async def fail(self, *args: object, **kwargs: object) -> JobState:
        del args, kwargs
        self.failed = True
        return JobState.FAILED


def _dispatch() -> JobDispatch:
    return JobDispatch(
        task_name=VIDEO_RENDER_TASK_NAME,
        queue=VIDEO_RENDER_QUEUE,
        message=JobMessage(
            job_id=UUID("00000000-0000-0000-0000-000000000003"),
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            project_id=UUID("00000000-0000-0000-0000-000000000002"),
            operation_id=UUID("00000000-0000-0000-0000-000000000004"),
            trace_id="trace-video-wake",
        ),
    )


def test_due_wait_copies_canonical_dispatch_and_uses_state_version_identity(monkeypatch: object) -> None:
    dispatch = _dispatch()
    task = {
        "id": dispatch.message.job_id,
        "organization_id": dispatch.message.organization_id,
        "project_id": dispatch.message.project_id,
        "state_version": 7,
    }
    connection = FakeWakeConnection(task=task, dispatch=dispatch)

    async def fake_connect(dsn: str) -> FakeWakeConnection:
        assert dsn == "postgresql://test"
        return connection

    monkeypatch.setattr("lumi_worker_media.external_wait_runtime.asyncpg.connect", fake_connect)  # type: ignore[attr-defined]
    scheduler = MediaExternalWaitWakeScheduler("postgresql://test")

    wakes = asyncio.run(scheduler.stage_due_batch())

    assert len(wakes) == 1
    expected_event = uuid5(dispatch.message.job_id, "lumi:external-wake:8")
    assert wakes[0].event_id == expected_event
    assert wakes[0].state_version == 8
    assert connection.inserted_event_ids == [expected_event]
    assert connection.closed is True

    # Same wait cycle is no longer due after staging, so another scheduler pass
    # cannot fabricate a duplicate outbox event.
    assert asyncio.run(scheduler.stage_due_batch()) == ()
    assert connection.inserted_event_ids == [expected_event]


def test_execute_job_parks_external_wait_without_success_or_failure() -> None:
    message = _dispatch().message
    store = FakeJobStore()
    wait = ExternalWait(
        wait_reason="provider_async_render",
        external_ref="provider-job-123",
        retry_not_before=datetime.now(UTC) + timedelta(seconds=30),
        output={"video_job_id": "video-job-1"},
    )

    async def handler(value: JobMessage) -> ExternalWait:
        assert value == message
        return wait

    outcome = asyncio.run(
        execute_job(
            store=cast(TaskJobStore, store),
            message=message,
            handler=handler,
        )
    )

    assert outcome.state == JobState.WAITING_EXTERNAL
    assert outcome.attempt_count == 1
    assert outcome.output == {"video_job_id": "video-job-1"}
    assert store.waits == [wait]
    assert store.succeeded is False
    assert store.failed is False
