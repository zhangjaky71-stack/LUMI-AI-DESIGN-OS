from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import StrEnum


class PerformanceStage(StrEnum):
    ENQUEUE = "enqueue"
    ROUTING = "routing"
    PROVIDER = "provider"
    DOWNLOAD = "download"
    POSTPROCESS = "postprocess"
    VALIDATION = "validation"
    ARTIFACT_PERSIST = "artifact_persist"
    UI_PROPAGATION = "ui_propagation"
    PLATFORM_OVERHEAD = "platform_overhead"


class PerformanceOutcome(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


_STAGE_LOGGER = logging.getLogger("lumi.performance.stage")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SERVICE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class PerformanceTelemetryContext:
    performance_run_id: str
    profile_id: str
    source_rc_sha: str

    def __post_init__(self) -> None:
        _require_identifier("performance_run_id", self.performance_run_id)
        if self.profile_id not in {"A", "B", "C", "D", "E", "F", "G"}:
            raise ValueError("profile_id must be one of A..G")
        if not _SHA40_RE.fullmatch(self.source_rc_sha):
            raise ValueError("source_rc_sha must be an exact lowercase SHA-40")

    @classmethod
    def from_environ(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> PerformanceTelemetryContext | None:
        env = os.environ if environ is None else environ
        raw_enabled = env.get("LUMI_PERFORMANCE_TELEMETRY_ENABLED", "").strip().lower()
        if raw_enabled in _FALSE:
            return None
        if raw_enabled not in _TRUE:
            raise ValueError("LUMI_PERFORMANCE_TELEMETRY_ENABLED must be an explicit boolean")

        run_id = env.get("LUMI_PERFORMANCE_RUN_ID", "").strip()
        profile_id = env.get("LUMI_PERFORMANCE_PROFILE_ID", "").strip()
        source_rc_sha = env.get("LUMI_PERFORMANCE_SOURCE_RC_SHA", "").strip()
        if not run_id or not profile_id or not source_rc_sha:
            raise ValueError(
                "enabled performance telemetry requires run id, profile id, and Source RC SHA"
            )
        return cls(
            performance_run_id=run_id,
            profile_id=profile_id,
            source_rc_sha=source_rc_sha,
        )


@dataclass(frozen=True, slots=True)
class PerformanceStageEvent:
    schema_version: int
    performance_run_id: str
    profile_id: str
    source_rc_sha: str
    operation_id: str
    task_id: str | None
    service: str
    stage: PerformanceStage
    started_at_unix_ns: int
    completed_at_unix_ns: int
    duration_ms: float
    outcome: PerformanceOutcome
    attempt: int

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("schema_version must equal 1")
        PerformanceTelemetryContext(
            performance_run_id=self.performance_run_id,
            profile_id=self.profile_id,
            source_rc_sha=self.source_rc_sha,
        )
        _require_identifier("operation_id", self.operation_id)
        if self.task_id is not None:
            _require_identifier("task_id", self.task_id)
        if not _SERVICE_RE.fullmatch(self.service):
            raise ValueError("service must be a bounded machine identifier")
        if self.started_at_unix_ns < 0:
            raise ValueError("started_at_unix_ns must be non-negative")
        if self.completed_at_unix_ns < self.started_at_unix_ns:
            raise ValueError("completed_at_unix_ns must not precede start")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if self.attempt < 1:
            raise ValueError("attempt must be at least 1")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["stage"] = self.stage.value
        payload["outcome"] = self.outcome.value
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


PerformanceEventSink = Callable[[PerformanceStageEvent], None]


def _require_identifier(name: str, value: str) -> None:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{name} must be a bounded machine identifier")


def _default_sink(event: PerformanceStageEvent) -> None:
    _STAGE_LOGGER.info("LUMI_PERF_STAGE %s", event.to_json())


def emit_performance_interval(
    context: PerformanceTelemetryContext | None,
    *,
    stage: PerformanceStage,
    service: str,
    operation_id: str,
    started_at_unix_ns: int,
    completed_at_unix_ns: int,
    task_id: str | None = None,
    outcome: PerformanceOutcome = PerformanceOutcome.SUCCESS,
    attempt: int = 1,
    sink: PerformanceEventSink | None = None,
) -> PerformanceStageEvent | None:
    if context is None:
        return None
    event = PerformanceStageEvent(
        schema_version=1,
        performance_run_id=context.performance_run_id,
        profile_id=context.profile_id,
        source_rc_sha=context.source_rc_sha,
        operation_id=operation_id,
        task_id=task_id,
        service=service,
        stage=stage,
        started_at_unix_ns=started_at_unix_ns,
        completed_at_unix_ns=completed_at_unix_ns,
        duration_ms=(completed_at_unix_ns - started_at_unix_ns) / 1_000_000,
        outcome=outcome,
        attempt=attempt,
    )
    (sink or _default_sink)(event)
    return event


@contextmanager
def measure_performance_stage(
    context: PerformanceTelemetryContext | None,
    *,
    stage: PerformanceStage,
    service: str,
    operation_id: str,
    task_id: str | None = None,
    attempt: int = 1,
    sink: PerformanceEventSink | None = None,
) -> Iterator[None]:
    if context is None:
        yield
        return

    _require_identifier("operation_id", operation_id)
    if task_id is not None:
        _require_identifier("task_id", task_id)
    if not _SERVICE_RE.fullmatch(service):
        raise ValueError("service must be a bounded machine identifier")
    if attempt < 1:
        raise ValueError("attempt must be at least 1")

    started_wall_ns = time.time_ns()
    started_monotonic_ns = time.perf_counter_ns()
    outcome = PerformanceOutcome.SUCCESS
    try:
        yield
    except BaseException:
        outcome = PerformanceOutcome.ERROR
        raise
    finally:
        completed_wall_ns = time.time_ns()
        elapsed_ns = time.perf_counter_ns() - started_monotonic_ns
        event = PerformanceStageEvent(
            schema_version=1,
            performance_run_id=context.performance_run_id,
            profile_id=context.profile_id,
            source_rc_sha=context.source_rc_sha,
            operation_id=operation_id,
            task_id=task_id,
            service=service,
            stage=stage,
            started_at_unix_ns=started_wall_ns,
            completed_at_unix_ns=max(completed_wall_ns, started_wall_ns),
            duration_ms=elapsed_ns / 1_000_000,
            outcome=outcome,
            attempt=attempt,
        )
        (sink or _default_sink)(event)
