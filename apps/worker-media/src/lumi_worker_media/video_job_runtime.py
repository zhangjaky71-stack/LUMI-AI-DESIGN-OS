from __future__ import annotations

from typing import Protocol

from .job_runtime import ExternalWait, JobOutcome, TaskJobStore
from .queue_contracts import ErrorCategory, JobMessage, JobState, classify_error


class HostedVideoJobHandler(Protocol):
    async def execute(self, message: JobMessage) -> dict[str, object] | ExternalWait: ...

    async def reconcile_cancellation(
        self,
        message: JobMessage,
    ) -> dict[str, object] | ExternalWait: ...


async def execute_video_job(
    *,
    store: TaskJobStore,
    message: JobMessage,
    runtime: HostedVideoJobHandler,
) -> JobOutcome:
    """Run video.render without equating a cancellation request to provider cancellation."""

    cancellation_before_claim = await store.cancellation_requested(message)
    attempt_count = await store.claim(message)
    if attempt_count is None:
        return JobOutcome(
            JobState.CANCELLED,
            0,
            {
                "cancelled": cancellation_before_claim,
                "skipped": "not_claimable",
            },
        )

    try:
        if cancellation_before_claim:
            return await _reconcile_cancellation(
                store=store,
                message=message,
                runtime=runtime,
                attempt_count=attempt_count,
            )

        result = await runtime.execute(message)
        if await store.cancellation_requested(message):
            return await _reconcile_cancellation(
                store=store,
                message=message,
                runtime=runtime,
                attempt_count=attempt_count,
            )
        if isinstance(result, ExternalWait):
            await store.wait_external(message, result)
            return JobOutcome(JobState.WAITING_EXTERNAL, attempt_count, dict(result.output))
        output = dict(result)
        await store.succeed(message, output)
        return JobOutcome(JobState.SUCCEEDED, attempt_count, output)
    except Exception as exc:
        category = classify_error(
            code=getattr(exc, "code", type(exc).__name__),
            retryable=getattr(exc, "retryable", None),
        )
        state = await store.fail(
            message,
            category=category,
            error_code=str(getattr(exc, "code", type(exc).__name__)),
            error_message=str(exc),
        )
        return JobOutcome(state, attempt_count, {"error": str(exc)})


async def _reconcile_cancellation(
    *,
    store: TaskJobStore,
    message: JobMessage,
    runtime: HostedVideoJobHandler,
    attempt_count: int,
) -> JobOutcome:
    resolution = await runtime.reconcile_cancellation(message)
    if isinstance(resolution, ExternalWait):
        await store.wait_external(message, resolution)
        return JobOutcome(
            JobState.WAITING_EXTERNAL,
            attempt_count,
            {
                **dict(resolution.output),
                "cancellation_pending": True,
            },
        )

    output = dict(resolution)
    status = str(output.get("status", "")).upper()
    if status == "CANCELLED":
        await store.cancel(message)
        return JobOutcome(JobState.CANCELLED, attempt_count, output)
    if status in {"COMPLETED", "PARTIAL"}:
        output["cancellation_request_lost_race_to_terminal"] = True
        await store.succeed(message, output)
        return JobOutcome(JobState.SUCCEEDED, attempt_count, output)
    if status == "FAILED":
        error_code = str(output.get("error_code") or "VIDEO_GENERATION_FAILED")
        state = await store.fail(
            message,
            category=ErrorCategory.PERMANENT,
            error_code=error_code,
            error_message="provider video reached terminal failure during cancellation reconciliation",
        )
        return JobOutcome(state, attempt_count, output)
    raise RuntimeError("VIDEO_CANCELLATION_RECONCILIATION_STATE_INVALID")


__all__ = ["HostedVideoJobHandler", "execute_video_job"]
