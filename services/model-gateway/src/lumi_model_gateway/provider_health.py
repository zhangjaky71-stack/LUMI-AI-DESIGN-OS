from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from .models import TelemetryEvent


class ProviderHealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OPEN = "open"
    HALF_OPEN = "half_open"


class HealthClock(Protocol):
    def monotonic(self) -> float: ...


class SystemHealthClock:
    def monotonic(self) -> float:
        return time.monotonic()


@dataclass(frozen=True, slots=True)
class ProviderHealthPolicy:
    window_seconds: float = 60.0
    max_samples: int = 100
    minimum_samples: int = 5
    degraded_failure_rate: float = 0.20
    open_failure_rate: float = 0.50
    consecutive_failures_open: int = 4
    open_cooldown_seconds: float = 30.0
    half_open_successes_to_close: int = 2
    half_open_max_probes: int = 1
    degraded_latency_ms: int = 8_000

    def __post_init__(self) -> None:
        if self.window_seconds <= 0:
            raise ValueError("PROVIDER_HEALTH_WINDOW_INVALID")
        if self.max_samples < 1 or self.minimum_samples < 1:
            raise ValueError("PROVIDER_HEALTH_SAMPLE_LIMIT_INVALID")
        if self.minimum_samples > self.max_samples:
            raise ValueError("PROVIDER_HEALTH_MINIMUM_EXCEEDS_WINDOW")
        if not 0 <= self.degraded_failure_rate <= self.open_failure_rate <= 1:
            raise ValueError("PROVIDER_HEALTH_FAILURE_RATE_INVALID")
        if self.consecutive_failures_open < 1:
            raise ValueError("PROVIDER_HEALTH_CONSECUTIVE_FAILURES_INVALID")
        if self.open_cooldown_seconds <= 0:
            raise ValueError("PROVIDER_HEALTH_COOLDOWN_INVALID")
        if self.half_open_successes_to_close < 1 or self.half_open_max_probes < 1:
            raise ValueError("PROVIDER_HEALTH_HALF_OPEN_POLICY_INVALID")
        if self.degraded_latency_ms < 1:
            raise ValueError("PROVIDER_HEALTH_LATENCY_INVALID")


@dataclass(frozen=True, slots=True)
class ProviderHealthObservation:
    observed_monotonic: float
    success: bool
    latency_ms: int
    error_category: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderHealthSnapshot:
    provider: str
    model: str
    state: ProviderHealthState
    score: int
    sample_count: int
    failure_rate: float
    consecutive_failures: int
    latency_p95_ms: int | None
    open_until_monotonic: float | None
    half_open_inflight: int
    half_open_successes: int
    updated_monotonic: float


@dataclass(slots=True)
class _HealthRecord:
    state: ProviderHealthState = ProviderHealthState.HEALTHY
    samples: deque[ProviderHealthObservation] = field(default_factory=deque)
    consecutive_failures: int = 0
    open_until: float | None = None
    half_open_inflight: int = 0
    half_open_successes: int = 0
    updated_at: float = 0.0


_IGNORED_ERROR_CATEGORIES = frozenset(
    {
        "invalid_request",
        "content_policy",
        "budget_exceeded",
        "cancelled",
        "client_cancelled",
    }
)
_RATE_LIMIT_CATEGORIES = frozenset({"rate_limited", "rate_limit", "provider_429"})


class AdaptiveProviderHealthRegistry:
    """Thread-safe provider/model health state machine for routing and circuit control."""

    def __init__(
        self,
        *,
        policy: ProviderHealthPolicy | None = None,
        clock: HealthClock | None = None,
    ) -> None:
        self.policy = policy or ProviderHealthPolicy()
        self.clock = clock or SystemHealthClock()
        self._records: dict[str, _HealthRecord] = {}
        self._lock = threading.RLock()

    def health_score(self, provider: str, model: str) -> int:
        return self.snapshot(provider, model).score

    def score(self, provider: str, model: str) -> int:
        return self.health_score(provider, model)

    def get_score(self, provider: str, model: str) -> int:
        return self.health_score(provider, model)

    def is_available(self, provider: str, model: str) -> bool:
        return self.snapshot(provider, model).state != ProviderHealthState.OPEN

    def record_success(self, provider: str, model: str, *, latency_ms: int) -> None:
        if latency_ms < 0:
            raise ValueError("PROVIDER_HEALTH_LATENCY_NEGATIVE")
        now = self.clock.monotonic()
        with self._lock:
            record = self._record(provider, model, now)
            self._refresh_state(record, now)
            self._append(
                record,
                ProviderHealthObservation(now, True, latency_ms),
                now,
            )
            record.consecutive_failures = 0
            if record.state == ProviderHealthState.HALF_OPEN:
                if record.half_open_inflight > 0:
                    record.half_open_inflight -= 1
                record.half_open_successes += 1
                if (
                    record.half_open_successes
                    >= self.policy.half_open_successes_to_close
                ):
                    self._close(record, now)
                    return
            self._evaluate(record, now)

    def record_failure(
        self,
        provider: str,
        model: str,
        *,
        error_category: str,
        latency_ms: int = 0,
        retry_after_seconds: float | None = None,
    ) -> None:
        normalized = error_category.strip().lower()
        if normalized in _IGNORED_ERROR_CATEGORIES:
            return
        if latency_ms < 0:
            raise ValueError("PROVIDER_HEALTH_LATENCY_NEGATIVE")
        if retry_after_seconds is not None and retry_after_seconds < 0:
            raise ValueError("PROVIDER_HEALTH_RETRY_AFTER_INVALID")
        now = self.clock.monotonic()
        with self._lock:
            record = self._record(provider, model, now)
            self._refresh_state(record, now)
            self._append(
                record,
                ProviderHealthObservation(
                    now,
                    False,
                    latency_ms,
                    normalized,
                ),
                now,
            )
            record.consecutive_failures += 1
            if record.state == ProviderHealthState.HALF_OPEN:
                if record.half_open_inflight > 0:
                    record.half_open_inflight -= 1
                self._open(record, now, retry_after_seconds=retry_after_seconds)
                return
            if normalized in _RATE_LIMIT_CATEGORIES and retry_after_seconds:
                self._open(record, now, retry_after_seconds=retry_after_seconds)
                return
            self._evaluate(record, now)

    def record_telemetry(
        self,
        event: TelemetryEvent,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        if event.error_category is None:
            self.record_success(
                event.provider,
                event.model,
                latency_ms=event.latency_ms,
            )
            return
        self.record_failure(
            event.provider,
            event.model,
            error_category=event.error_category,
            latency_ms=event.latency_ms,
            retry_after_seconds=retry_after_seconds,
        )

    def acquire_probe(self, provider: str, model: str) -> bool:
        now = self.clock.monotonic()
        with self._lock:
            record = self._record(provider, model, now)
            self._refresh_state(record, now)
            if record.state == ProviderHealthState.OPEN:
                return False
            if record.state != ProviderHealthState.HALF_OPEN:
                return True
            if record.half_open_inflight >= self.policy.half_open_max_probes:
                return False
            record.half_open_inflight += 1
            record.updated_at = now
            return True

    def release_probe(self, provider: str, model: str) -> None:
        now = self.clock.monotonic()
        with self._lock:
            record = self._record(provider, model, now)
            if record.half_open_inflight > 0:
                record.half_open_inflight -= 1
            record.updated_at = now

    def snapshot(self, provider: str, model: str) -> ProviderHealthSnapshot:
        now = self.clock.monotonic()
        with self._lock:
            record = self._record(provider, model, now)
            self._refresh_state(record, now)
            self._prune(record, now)
            failures = sum(1 for item in record.samples if not item.success)
            sample_count = len(record.samples)
            failure_rate = failures / sample_count if sample_count else 0.0
            latency_p95 = _p95(
                [item.latency_ms for item in record.samples if item.success]
            )
            score = self._score(
                state=record.state,
                failure_rate=failure_rate,
                latency_p95_ms=latency_p95,
            )
            return ProviderHealthSnapshot(
                provider=provider,
                model=model,
                state=record.state,
                score=score,
                sample_count=sample_count,
                failure_rate=failure_rate,
                consecutive_failures=record.consecutive_failures,
                latency_p95_ms=latency_p95,
                open_until_monotonic=record.open_until,
                half_open_inflight=record.half_open_inflight,
                half_open_successes=record.half_open_successes,
                updated_monotonic=record.updated_at,
            )

    def reset(self, provider: str, model: str) -> None:
        with self._lock:
            self._records.pop(_key(provider, model), None)

    def _record(self, provider: str, model: str, now: float) -> _HealthRecord:
        key = _key(provider, model)
        record = self._records.get(key)
        if record is None:
            record = _HealthRecord(updated_at=now)
            self._records[key] = record
        return record

    def _append(
        self,
        record: _HealthRecord,
        observation: ProviderHealthObservation,
        now: float,
    ) -> None:
        record.samples.append(observation)
        record.updated_at = now
        self._prune(record, now)
        while len(record.samples) > self.policy.max_samples:
            record.samples.popleft()

    def _prune(self, record: _HealthRecord, now: float) -> None:
        cutoff = now - self.policy.window_seconds
        while record.samples and record.samples[0].observed_monotonic < cutoff:
            record.samples.popleft()

    def _evaluate(self, record: _HealthRecord, now: float) -> None:
        if record.state in {ProviderHealthState.OPEN, ProviderHealthState.HALF_OPEN}:
            return
        self._prune(record, now)
        samples = len(record.samples)
        failures = sum(1 for item in record.samples if not item.success)
        failure_rate = failures / samples if samples else 0.0
        latency_p95 = _p95(
            [item.latency_ms for item in record.samples if item.success]
        )
        if record.consecutive_failures >= self.policy.consecutive_failures_open:
            self._open(record, now)
            return
        if (
            samples >= self.policy.minimum_samples
            and failure_rate >= self.policy.open_failure_rate
        ):
            self._open(record, now)
            return
        degraded = (
            samples >= self.policy.minimum_samples
            and failure_rate >= self.policy.degraded_failure_rate
        ) or (
            latency_p95 is not None
            and latency_p95 >= self.policy.degraded_latency_ms
        )
        record.state = (
            ProviderHealthState.DEGRADED if degraded else ProviderHealthState.HEALTHY
        )
        record.updated_at = now

    def _refresh_state(self, record: _HealthRecord, now: float) -> None:
        if (
            record.state == ProviderHealthState.OPEN
            and record.open_until is not None
            and now >= record.open_until
        ):
            record.state = ProviderHealthState.HALF_OPEN
            record.open_until = None
            record.half_open_inflight = 0
            record.half_open_successes = 0
            record.updated_at = now

    def _open(
        self,
        record: _HealthRecord,
        now: float,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        cooldown = max(
            self.policy.open_cooldown_seconds,
            retry_after_seconds or 0.0,
        )
        record.state = ProviderHealthState.OPEN
        record.open_until = now + cooldown
        record.half_open_inflight = 0
        record.half_open_successes = 0
        record.updated_at = now

    def _close(self, record: _HealthRecord, now: float) -> None:
        record.state = ProviderHealthState.HEALTHY
        record.open_until = None
        record.half_open_inflight = 0
        record.half_open_successes = 0
        record.consecutive_failures = 0
        record.samples.clear()
        record.updated_at = now

    def _score(
        self,
        *,
        state: ProviderHealthState,
        failure_rate: float,
        latency_p95_ms: int | None,
    ) -> int:
        if state == ProviderHealthState.OPEN:
            return 0
        if state == ProviderHealthState.HALF_OPEN:
            return 20
        failure_penalty = round(failure_rate * 70)
        latency_penalty = 0
        if latency_p95_ms is not None and latency_p95_ms > self.policy.degraded_latency_ms:
            ratio = latency_p95_ms / self.policy.degraded_latency_ms
            latency_penalty = min(25, round((ratio - 1) * 20))
        score = 100 - failure_penalty - latency_penalty
        if state == ProviderHealthState.DEGRADED:
            score = min(score, 70)
        return max(1, min(100, score))


def _key(provider: str, model: str) -> str:
    if not provider or not model:
        raise ValueError("PROVIDER_HEALTH_KEY_INVALID")
    return f"{provider}:{model}"


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]
