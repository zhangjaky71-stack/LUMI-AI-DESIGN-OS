from uuid import uuid4

import pytest

from lumi_worker_media.queue_contracts import (
    ErrorCategory,
    JobKind,
    JobMessage,
    classify_error,
    queue_for,
    retry_policy_for,
    validate_job_payload,
)


def test_job_message_is_ids_only_and_routes_to_separated_queue() -> None:
    message = JobMessage.from_mapping(
        {
            "job_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "project_id": str(uuid4()),
            "operation_id": str(uuid4()),
        }
    )
    assert message.operation_id is not None
    assert queue_for(JobKind.VIDEO_RENDER) == "lumi.media.video"
    assert queue_for(JobKind.ASSET_VALIDATE) == "lumi.asset.processing"


def test_binary_secret_and_large_payloads_are_rejected() -> None:
    with pytest.raises(ValueError, match="BINARY_FORBIDDEN"):
        validate_job_payload({"blob": b"binary"})
    with pytest.raises(ValueError, match="SECRET_FIELD_FORBIDDEN"):
        validate_job_payload({"provider_secret": "never-on-broker"})
    with pytest.raises(ValueError, match="TOO_LARGE"):
        validate_job_payload({"text": "x" * (65 * 1024)})


def test_retry_policy_and_error_classification_are_explicit() -> None:
    video = retry_policy_for(JobKind.VIDEO_RENDER)
    assert video.provider_reconciliation_required is True
    assert video.delay_seconds(attempt=2) > video.delay_seconds(attempt=1)
    assert classify_error(code="PROVIDER_503", retryable=None) == ErrorCategory.TRANSIENT
    assert classify_error(code="INVALID_INPUT", retryable=None) == ErrorCategory.PERMANENT
