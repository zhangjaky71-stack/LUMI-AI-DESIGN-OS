from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

MAX_JOB_MESSAGE_BYTES = 64 * 1024
JOB_DISPATCH_EVENT_NAME = "job.dispatch.requested"
JOB_DISPATCH_SCHEMA_VERSION = 1

IMAGE_TRANSFORM_JOB_KIND = "image.transform"
IMAGE_TRANSFORM_TASK_NAME = "lumi.jobs.image.transform"
IMAGE_TRANSFORM_QUEUE = "lumi.media.image"
IMAGE_TRANSFORM_ROUTING_KEY = "image.transform"


@dataclass(frozen=True, slots=True)
class JobMessage:
    """Canonical cross-process job reference envelope.

    Broker messages carry durable identifiers only. Business payloads, provider
    credentials, prompts, and binary media belong in durable stores and are
    resolved by the consumer after tenant-scoped lookup.
    """

    job_id: UUID
    organization_id: UUID
    project_id: UUID
    operation_id: UUID | None = None
    trace_id: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        payload = {
            "job_id": str(self.job_id),
            "organization_id": str(self.organization_id),
            "project_id": str(self.project_id),
            "operation_id": str(self.operation_id) if self.operation_id else None,
            "trace_id": self.trace_id,
        }
        validate_job_payload(payload)
        return payload

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> JobMessage:
        allowed = {"job_id", "organization_id", "project_id", "operation_id", "trace_id"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"JOB_MESSAGE_UNKNOWN_FIELDS:{','.join(sorted(unknown))}")
        for required in ("job_id", "organization_id", "project_id"):
            if not value.get(required):
                raise ValueError(f"JOB_MESSAGE_REQUIRED:{required}")
        message = cls(
            job_id=UUID(str(value["job_id"])),
            organization_id=UUID(str(value["organization_id"])),
            project_id=UUID(str(value["project_id"])),
            operation_id=UUID(str(value["operation_id"])) if value.get("operation_id") else None,
            trace_id=str(value["trace_id"]) if value.get("trace_id") else None,
        )
        validate_job_payload(message.as_dict())
        return message


@dataclass(frozen=True, slots=True)
class JobDispatch:
    """Strict outbox-to-broker envelope for one positional JobMessage argument."""

    task_name: str
    queue: str
    message: JobMessage

    def as_outbox_payload(self) -> dict[str, object]:
        if not self.task_name or len(self.task_name) > 150:
            raise ValueError("JOB_DISPATCH_TASK_NAME_INVALID")
        if not self.queue or len(self.queue) > 150:
            raise ValueError("JOB_DISPATCH_QUEUE_INVALID")
        payload: dict[str, object] = {
            "task_name": self.task_name,
            "queue": self.queue,
            "args": [self.message.as_dict()],
            "kwargs": {},
        }
        validate_job_payload(payload)
        return payload

    @classmethod
    def from_outbox_payload(cls, value: object) -> JobDispatch:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ValueError("JOB_DISPATCH_PAYLOAD_OBJECT_REQUIRED")
        allowed = {"task_name", "queue", "args", "kwargs"}
        unknown = set(value) - allowed
        missing = allowed - set(value)
        if unknown:
            raise ValueError(f"JOB_DISPATCH_UNKNOWN_FIELDS:{','.join(sorted(unknown))}")
        if missing:
            raise ValueError(f"JOB_DISPATCH_REQUIRED:{','.join(sorted(missing))}")
        task_name = value["task_name"]
        queue = value["queue"]
        if not isinstance(task_name, str) or not task_name or len(task_name) > 150:
            raise ValueError("JOB_DISPATCH_TASK_NAME_INVALID")
        if not isinstance(queue, str) or not queue or len(queue) > 150:
            raise ValueError("JOB_DISPATCH_QUEUE_INVALID")
        args = value["args"]
        if not isinstance(args, list) or len(args) != 1 or not isinstance(args[0], dict):
            raise ValueError("JOB_DISPATCH_ARGS_INVALID")
        kwargs = value["kwargs"]
        if not isinstance(kwargs, dict) or kwargs:
            raise ValueError("JOB_DISPATCH_KWARGS_FORBIDDEN")
        validate_job_payload(value)
        return cls(
            task_name=task_name,
            queue=queue,
            message=JobMessage.from_mapping(args[0]),
        )


def validate_job_payload(payload: Any) -> None:
    _reject_binary_or_secret(payload, path="$", depth=0)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JOB_MESSAGE_BYTES:
        raise ValueError("JOB_MESSAGE_TOO_LARGE")


def _reject_binary_or_secret(value: Any, *, path: str, depth: int) -> None:
    if depth > 12:
        raise ValueError("JOB_MESSAGE_TOO_DEEP")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"JOB_MESSAGE_BINARY_FORBIDDEN:{path}")
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            forbidden = ("secret", "password", "api_key", "access_token")
            if any(token in key_text for token in forbidden):
                raise ValueError(f"JOB_MESSAGE_SECRET_FIELD_FORBIDDEN:{path}.{key}")
            _reject_binary_or_secret(child, path=f"{path}.{key}", depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_binary_or_secret(child, path=f"{path}[{index}]", depth=depth + 1)
        return
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise ValueError(f"JOB_MESSAGE_NON_JSON_VALUE:{path}")
