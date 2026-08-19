from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

MAX_JOB_MESSAGE_BYTES = 64 * 1024


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
