from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from lumi_worker_media import app
from lumi_worker_media.job_runtime import JobOutcome
from lumi_worker_media.queue_contracts import JobState

MESSAGE = {
    "job_id": "11111111-1111-1111-1111-111111111111",
    "organization_id": "22222222-2222-2222-2222-222222222222",
    "project_id": "33333333-3333-3333-3333-333333333333",
    "operation_id": "44444444-4444-4444-4444-444444444444",
    "trace_id": "unit-image-entrypoint",
}


def test_image_task_returns_durable_success_payload() -> None:
    outcome = JobOutcome(
        state=JobState.SUCCEEDED,
        attempt_count=2,
        output={
            "generation_id": "image-generation:" + "a" * 64,
            "status": "COMPLETED",
            "artifact_count": 1,
        },
    )
    with patch.object(
        app,
        "_execute_image_generation_job",
        new=AsyncMock(return_value=outcome),
    ) as execute:
        payload = app.image_transform.run(MESSAGE)
    assert payload["job_id"] == MESSAGE["job_id"]
    assert payload["state"] == "succeeded"
    assert payload["attempt_count"] == 2
    assert payload["status"] == "COMPLETED"
    parsed = execute.await_args.args[0]
    assert parsed.job_id == UUID(MESSAGE["job_id"])
    assert parsed.operation_id == UUID(MESSAGE["operation_id"])
    assert "accepted" not in payload.values()


def test_image_task_failed_outcome_raises_for_celery_dlq() -> None:
    outcome = JobOutcome(
        state=JobState.FAILED,
        attempt_count=4,
        output={"error": "GENERATION_NO_READY_CANDIDATES"},
    )
    with patch.object(
        app,
        "_execute_image_generation_job",
        new=AsyncMock(return_value=outcome),
    ):
        with pytest.raises(RuntimeError, match="IMAGE_GENERATION_JOB_FAILED"):
            app.image_transform.run(MESSAGE)


def test_image_task_retrying_outcome_calls_celery_retry() -> None:
    outcome = JobOutcome(
        state=JobState.RETRYING,
        attempt_count=2,
        output={"error": "MODEL_GATEWAY_TEMPORARY"},
    )
    with (
        patch.object(
            app,
            "_execute_image_generation_job",
            new=AsyncMock(return_value=outcome),
        ),
        patch.object(
            app.image_transform,
            "retry",
            side_effect=RuntimeError("retry-called"),
        ) as retry,
    ):
        with pytest.raises(RuntimeError, match="retry-called"):
            app.image_transform.run(MESSAGE)
    assert retry.call_count == 1
    kwargs = retry.call_args.kwargs
    assert isinstance(kwargs["exc"], RuntimeError)
    assert kwargs["countdown"] >= 2
