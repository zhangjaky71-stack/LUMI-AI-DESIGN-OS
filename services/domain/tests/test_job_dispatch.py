from __future__ import annotations

from uuid import uuid4

import pytest

from lumi_domain.job_dispatch import JobMessage, validate_job_payload


def _payload() -> dict[str, str | None]:
    return {
        "job_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "project_id": str(uuid4()),
        "operation_id": str(uuid4()),
        "trace_id": "trace-123",
    }


def test_job_message_round_trips_exact_reference_fields() -> None:
    payload = _payload()
    message = JobMessage.from_mapping(payload)

    assert message.as_dict() == payload
    assert set(message.as_dict()) == {
        "job_id",
        "organization_id",
        "project_id",
        "operation_id",
        "trace_id",
    }


def test_job_message_rejects_unknown_business_payload() -> None:
    payload = _payload()
    payload["prompt"] = "must stay in durable storage"

    with pytest.raises(ValueError, match="JOB_MESSAGE_UNKNOWN_FIELDS:prompt"):
        JobMessage.from_mapping(payload)


def test_job_message_rejects_missing_required_identity() -> None:
    payload = _payload()
    payload["project_id"] = None

    with pytest.raises(ValueError, match="JOB_MESSAGE_REQUIRED:project_id"):
        JobMessage.from_mapping(payload)


def test_job_payload_rejects_binary_and_secret_fields() -> None:
    with pytest.raises(ValueError, match="JOB_MESSAGE_BINARY_FORBIDDEN"):
        validate_job_payload({"blob": b"not-on-the-broker"})

    with pytest.raises(ValueError, match="JOB_MESSAGE_SECRET_FIELD_FORBIDDEN"):
        validate_job_payload({"provider_api_key": "do-not-serialize"})


def test_job_payload_rejects_message_larger_than_64_kib() -> None:
    with pytest.raises(ValueError, match="JOB_MESSAGE_TOO_LARGE"):
        validate_job_payload({"trace_id": "x" * (64 * 1024)})
