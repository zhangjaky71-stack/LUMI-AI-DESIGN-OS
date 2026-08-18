from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ObservabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SpanStatus(StrEnum):
    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


_SAFE_METRIC_ATTRIBUTE_KEYS = frozenset(
    {
        "service",
        "environment",
        "http.method",
        "http.route",
        "http.status_class",
        "outcome",
        "provider",
        "model_family",
        "capability",
        "queue",
        "worker",
        "operation_type",
        "error_code",
    }
)
_FORBIDDEN_ATTRIBUTE_MARKERS = (
    "prompt",
    "content",
    "password",
    "authorization",
    "token",
    "secret",
    "cookie",
    "api_key",
    "signed_url",
    "presigned",
    "file_body",
    "document_text",
    "reasoning",
)


def _safe_scalar(value: Any) -> str | int | float | bool:
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if len(value) > 256:
            raise ValueError("OBSERVABILITY_ATTRIBUTE_VALUE_TOO_LONG")
        normalized = value.casefold()
        if normalized.startswith(("bearer ", "sk-", "github_pat_", "ghp_")):
            raise ValueError("OBSERVABILITY_SECRET_ATTRIBUTE_FORBIDDEN")
        return value
    raise ValueError("OBSERVABILITY_ATTRIBUTE_SCALAR_REQUIRED")


def validate_safe_attributes(value: dict[str, Any]) -> dict[str, str | int | float | bool]:
    if len(value) > 48:
        raise ValueError("OBSERVABILITY_ATTRIBUTE_COUNT_EXCEEDED")
    result: dict[str, str | int | float | bool] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key or len(key) > 80:
            raise ValueError("OBSERVABILITY_ATTRIBUTE_KEY_INVALID")
        normalized = key.casefold().replace("-", "_")
        if any(marker in normalized for marker in _FORBIDDEN_ATTRIBUTE_MARKERS):
            raise ValueError("OBSERVABILITY_SENSITIVE_ATTRIBUTE_FORBIDDEN")
        result[key] = _safe_scalar(raw_value)
    return result


def validate_metric_attributes(value: dict[str, Any]) -> dict[str, str | int | float | bool]:
    unknown = sorted(set(value) - _SAFE_METRIC_ATTRIBUTE_KEYS)
    if unknown:
        raise ValueError(f"OBSERVABILITY_METRIC_HIGH_CARDINALITY_ATTRIBUTE:{','.join(unknown)}")
    return validate_safe_attributes(value)


class SpanRecord(ObservabilityModel):
    name: str = Field(min_length=1, max_length=160)
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    span_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    parent_span_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    status: SpanStatus = SpanStatus.UNSET
    started_at: datetime
    ended_at: datetime
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("attributes", mode="before")
    @classmethod
    def safe_attributes(cls, value: dict[str, Any]) -> dict[str, str | int | float | bool]:
        return validate_safe_attributes(value)

    @field_validator("started_at", "ended_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OBSERVABILITY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value


class MetricPoint(ObservabilityModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.]{1,159}$")
    value: int | float
    unit: str = Field(min_length=1, max_length=32)
    recorded_at: datetime
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("attributes", mode="before")
    @classmethod
    def bounded_metric_attributes(cls, value: dict[str, Any]) -> dict[str, str | int | float | bool]:
        return validate_metric_attributes(value)

    @field_validator("recorded_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OBSERVABILITY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value


class StructuredLogRecord(ObservabilityModel):
    level: LogLevel
    event: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,159}$")
    message: str = Field(min_length=1, max_length=512)
    occurred_at: datetime
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    span_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    request_id: str | None = Field(default=None, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)
    fields: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("fields", mode="before")
    @classmethod
    def safe_fields(cls, value: dict[str, Any]) -> dict[str, str | int | float | bool]:
        return validate_safe_attributes(value)

    @field_validator("occurred_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OBSERVABILITY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value
