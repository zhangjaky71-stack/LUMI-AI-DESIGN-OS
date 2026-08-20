from __future__ import annotations

import pytest

from lumi_domain.performance_events import (
    PerformanceOutcome,
    PerformanceStage,
    PerformanceTelemetryContext,
    emit_performance_interval,
    measure_performance_stage,
)


SHA = "1" * 40


def test_performance_telemetry_is_disabled_by_default() -> None:
    assert PerformanceTelemetryContext.from_environ({}) is None


def test_enabled_telemetry_requires_complete_provenance() -> None:
    with pytest.raises(ValueError, match="requires run id"):
        PerformanceTelemetryContext.from_environ(
            {"LUMI_PERFORMANCE_TELEMETRY_ENABLED": "true"}
        )


def test_enabled_telemetry_rejects_non_exact_source_sha() -> None:
    with pytest.raises(ValueError, match="SHA-40"):
        PerformanceTelemetryContext.from_environ(
            {
                "LUMI_PERFORMANCE_TELEMETRY_ENABLED": "1",
                "LUMI_PERFORMANCE_RUN_ID": "run-1",
                "LUMI_PERFORMANCE_PROFILE_ID": "C",
                "LUMI_PERFORMANCE_SOURCE_RC_SHA": "deadbeef",
            }
        )


def test_interval_event_contains_only_fixed_content_free_envelope() -> None:
    context = PerformanceTelemetryContext("run-1", "C", SHA)
    captured = []
    event = emit_performance_interval(
        context,
        stage=PerformanceStage.ENQUEUE,
        service="worker-media",
        operation_id="operation:1",
        task_id="task:1",
        started_at_unix_ns=1_000_000,
        completed_at_unix_ns=2_500_000,
        sink=captured.append,
    )
    assert event is not None
    assert captured == [event]
    assert event.duration_ms == 1.5
    assert set(event.to_dict()) == {
        "schema_version",
        "performance_run_id",
        "profile_id",
        "source_rc_sha",
        "operation_id",
        "task_id",
        "service",
        "stage",
        "started_at_unix_ns",
        "completed_at_unix_ns",
        "duration_ms",
        "outcome",
        "attempt",
    }
    serialized = event.to_json()
    for forbidden in ("prompt", "url", "filename", "provider_response", "signed_url"):
        assert forbidden not in serialized


def test_content_bearing_identifier_is_rejected() -> None:
    context = PerformanceTelemetryContext("run-1", "C", SHA)
    with pytest.raises(ValueError, match="machine identifier"):
        emit_performance_interval(
            context,
            stage=PerformanceStage.PROVIDER,
            service="worker-media",
            operation_id="draw a red cat with user prompt content",
            started_at_unix_ns=1,
            completed_at_unix_ns=2,
        )


def test_interval_rejects_clock_reversal() -> None:
    context = PerformanceTelemetryContext("run-1", "C", SHA)
    with pytest.raises(ValueError, match="must not precede"):
        emit_performance_interval(
            context,
            stage=PerformanceStage.ENQUEUE,
            service="worker-media",
            operation_id="operation:1",
            started_at_unix_ns=2,
            completed_at_unix_ns=1,
        )


def test_measured_stage_records_error_without_swallowing_exception() -> None:
    context = PerformanceTelemetryContext("run-1", "D", SHA)
    captured = []
    with pytest.raises(RuntimeError, match="boom"):
        with measure_performance_stage(
            context,
            stage=PerformanceStage.VALIDATION,
            service="worker-media",
            operation_id="operation:1",
            sink=captured.append,
        ):
            raise RuntimeError("boom")
    assert len(captured) == 1
    assert captured[0].outcome is PerformanceOutcome.ERROR
    assert captured[0].duration_ms >= 0


def test_disabled_measurement_emits_nothing() -> None:
    captured = []
    with measure_performance_stage(
        None,
        stage=PerformanceStage.PROVIDER,
        service="worker-media",
        operation_id="operation:1",
        sink=captured.append,
    ):
        pass
    assert captured == []
