from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from lumi_domain.job_dispatch import JobMessage
from lumi_worker_media.job_runtime import ExternalWait, TaskJobStore
from lumi_worker_media.queue_contracts import ErrorCategory, JobState
from lumi_worker_media.video_job_runtime import execute_video_job


def _message() -> JobMessage:
    return JobMessage(
        job_id=uuid4(),
        organization_id=uuid4(),
        project_id=uuid4(),
        operation_id=uuid4(),
        trace_id="video-cancel-reconcile-test",
    )


class _Store:
    def __init__(self, cancellations: list[bool], *, attempt_count: int = 1) -> None:
        self.cancellations = list(cancellations)
        self.attempt_count = attempt_count
        self.waits: list[ExternalWait] = []
        self.cancelled = 0
        self.succeeded: list[dict[str, object]] = []
        self.failures: list[tuple[ErrorCategory, str]] = []

    async def cancellation_requested(self, message: JobMessage) -> bool:
        del message
        return self.cancellations.pop(0) if self.cancellations else False

    async def claim(self, message: JobMessage) -> int | None:
        del message
        return self.attempt_count

    async def wait_external(self, message: JobMessage, wait: ExternalWait) -> None:
        del message
        self.waits.append(wait)

    async def cancel(self, message: JobMessage) -> None:
        del message
        self.cancelled += 1

    async def succeed(self, message: JobMessage, output: dict[str, object]) -> None:
        del message
        self.succeeded.append(dict(output))

    async def fail(
        self,
        message: JobMessage,
        *,
        category: ErrorCategory,
        error_code: str,
        error_message: str,
    ) -> JobState:
        del message, error_message
        self.failures.append((category, error_code))
        return JobState.FAILED


class _Runtime:
    def __init__(
        self,
        *,
        execute_result: dict[str, object] | ExternalWait,
        cancellation_result: dict[str, object] | ExternalWait,
    ) -> None:
        self.execute_result = execute_result
        self.cancellation_result = cancellation_result
        self.execute_calls = 0
        self.cancellation_calls = 0

    async def execute(self, message: JobMessage) -> dict[str, object] | ExternalWait:
        del message
        self.execute_calls += 1
        return self.execute_result

    async def reconcile_cancellation(
        self,
        message: JobMessage,
    ) -> dict[str, object] | ExternalWait:
        del message
        self.cancellation_calls += 1
        return self.cancellation_result


def _wait() -> ExternalWait:
    return ExternalWait(
        wait_reason="video_provider_pending",
        external_ref="video-provider:" + "a" * 64,
        retry_not_before=datetime.now(UTC) + timedelta(seconds=30),
        output={"status": "WAITING_EXTERNAL", "video_job_id": "video-job:test"},
    )


def test_video_cancel_request_stays_waiting_when_provider_cancel_is_unproven() -> None:
    async def run() -> None:
        store = _Store([True])
        runtime = _Runtime(
            execute_result={"status": "COMPLETED"},
            cancellation_result=_wait(),
        )
        outcome = await execute_video_job(
            store=cast(TaskJobStore, store),
            message=_message(),
            runtime=runtime,
        )
        assert outcome.state == JobState.WAITING_EXTERNAL
        assert outcome.output["cancellation_pending"] is True
        assert runtime.execute_calls == 0
        assert runtime.cancellation_calls == 1
        assert len(store.waits) == 1
        assert store.cancelled == 0
        assert store.succeeded == []

    asyncio.run(run())


def test_video_cancel_request_marks_cancelled_only_after_runtime_confirms() -> None:
    async def run() -> None:
        store = _Store([True])
        runtime = _Runtime(
            execute_result={"status": "COMPLETED"},
            cancellation_result={"status": "CANCELLED", "video_job_id": "video-job:test"},
        )
        outcome = await execute_video_job(
            store=cast(TaskJobStore, store),
            message=_message(),
            runtime=runtime,
        )
        assert outcome.state == JobState.CANCELLED
        assert store.cancelled == 1
        assert store.waits == []
        assert store.succeeded == []

    asyncio.run(run())


def test_provider_terminal_success_wins_race_with_late_cancel_request() -> None:
    async def run() -> None:
        store = _Store([False, True])
        runtime = _Runtime(
            execute_result={"status": "COMPLETED", "video_job_id": "video-job:test"},
            cancellation_result={"status": "COMPLETED", "video_job_id": "video-job:test"},
        )
        outcome = await execute_video_job(
            store=cast(TaskJobStore, store),
            message=_message(),
            runtime=runtime,
        )
        assert outcome.state == JobState.SUCCEEDED
        assert outcome.output["cancellation_request_lost_race_to_terminal"] is True
        assert runtime.execute_calls == 1
        assert runtime.cancellation_calls == 1
        assert len(store.succeeded) == 1
        assert store.cancelled == 0

    asyncio.run(run())


def test_invalid_video_cancellation_resolution_fails_closed() -> None:
    async def run() -> None:
        store = _Store([True])
        runtime = _Runtime(
            execute_result={"status": "COMPLETED"},
            cancellation_result={"status": "UNKNOWN"},
        )
        outcome = await execute_video_job(
            store=cast(TaskJobStore, store),
            message=_message(),
            runtime=runtime,
        )
        assert outcome.state == JobState.FAILED
        assert store.failures == [
            (ErrorCategory.PERMANENT, "RuntimeError"),
        ]
        assert store.cancelled == 0

    asyncio.run(run())
