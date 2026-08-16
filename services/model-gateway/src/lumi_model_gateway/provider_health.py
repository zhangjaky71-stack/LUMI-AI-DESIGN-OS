from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .models import HealthSnapshot
from .provider_health_store import HealthStateStore


class ProviderHealthState(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OPEN_CIRCUIT = "open_circuit"
    RECOVERING = "recovering"
    DISABLED = "disabled"


class ManualOverrideMode(StrEnum):
    DISABLED = "disabled"
    DEGRADED = "degraded"


class HealthClock(Protocol):
    def now(self) -> float: ...


class SystemHealthClock:
    def now(self) -> float:
        return time.time()


@dataclass(frozen=True, slots=True)
class ProviderHealthPolicy:
    window_seconds: float = 60.0
    max_samples: int = 100
    minimum_samples: int = 5
    degraded_failure_rate: float = 0.20
    open_failure_rate: float = 0.50
    degraded_rate_limit_rate: float = 0.10
    open_rate_limit_rate: float = 0.35
    degraded_timeout_rate: float = 0.10
    open_timeout_rate: float = 0.35
    consecutive_failures_open: int = 4
    open_cooldown_seconds: float = 30.0
    recovering_successes_to_close: int = 2
    recovering_max_probes: int = 1
    degraded_latency_p95_ms: int = 8_000
    state_ttl_seconds: float = 600.0
    unknown_score: int = 55
    recovering_score: int = 15

    def __post_init__(self) -> None:
        if self.window_seconds <= 0 or self.state_ttl_seconds <= 0:
            raise ValueError("PROVIDER_HEALTH_WINDOW_INVALID")
        if self.max_samples < 1 or self.minimum_samples < 1:
            raise ValueError("PROVIDER_HEALTH_SAMPLE_LIMIT_INVALID")
        if self.minimum_samples > self.max_samples:
            raise ValueError("PROVIDER_HEALTH_MINIMUM_EXCEEDS_WINDOW")
        pairs = (
            (self.degraded_failure_rate, self.open_failure_rate),
            (self.degraded_rate_limit_rate, self.open_rate_limit_rate),
            (self.degraded_timeout_rate, self.open_timeout_rate),
        )
        if any(not 0 <= degraded <= opened <= 1 for degraded, opened in pairs):
            raise ValueError("PROVIDER_HEALTH_RATE_THRESHOLD_INVALID")
        if self.consecutive_failures_open < 1:
            raise ValueError("PROVIDER_HEALTH_CONSECUTIVE_FAILURES_INVALID")
        if self.open_cooldown_seconds <= 0:
            raise ValueError("PROVIDER_HEALTH_COOLDOWN_INVALID")
        if self.recovering_successes_to_close < 1 or self.recovering_max_probes < 1:
            raise ValueError("PROVIDER_HEALTH_RECOVERY_POLICY_INVALID")
        if self.degraded_latency_p95_ms < 1:
            raise ValueError("PROVIDER_HEALTH_LATENCY_INVALID")
        if not 1 <= self.unknown_score <= 99 or not 1 <= self.recovering_score <= 99:
            raise ValueError("PROVIDER_HEALTH_SCORE_INVALID")


@dataclass(frozen=True, slots=True)
class CapacityHint:
    remaining: int | None = None
    limit: int | None = None
    reset_at_epoch: float | None = None
    retry_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.remaining is not None and self.remaining < 0:
            raise ValueError("PROVIDER_HEALTH_CAPACITY_REMAINING_INVALID")
        if self.limit is not None and self.limit < 0:
            raise ValueError("PROVIDER_HEALTH_CAPACITY_LIMIT_INVALID")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("PROVIDER_HEALTH_RETRY_AFTER_INVALID")


@dataclass(frozen=True, slots=True)
class ProviderHealthSnapshot:
    provider: str
    model: str | None
    capability: str | None
    state: ProviderHealthState
    score: int
    sample_count: int
    success_rate: float
    failure_rate: float
    rate_limit_rate: float
    timeout_rate: float
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    consecutive_failures: int
    open_until_epoch: float | None
    recovering_inflight: int
    recovering_successes: int
    capacity_hint: CapacityHint | None
    updated_at_epoch: float
    reason: str
    store_available: bool = True

    @property
    def routable(self) -> bool:
        return self.state not in {
            ProviderHealthState.OPEN_CIRCUIT,
            ProviderHealthState.DISABLED,
        }

    def to_gateway_snapshot(self) -> HealthSnapshot:
        return HealthSnapshot(
            healthy=self.routable,
            score=self.score,
            reason=f"provider_health:{self.state.value}:{self.reason}",
        )


@dataclass(frozen=True, slots=True)
class ProviderHealthTransition:
    provider: str
    model: str | None
    capability: str | None
    previous_state: ProviderHealthState
    current_state: ProviderHealthState
    score: int
    sample_count: int
    failure_rate: float
    latency_p95_ms: int | None
    observed_at_epoch: float
    reason: str


@dataclass(frozen=True, slots=True)
class ProviderHealthAuditEvent:
    action: str
    provider: str
    model: str | None
    capability: str | None
    actor_id: str
    reason: str
    observed_at_epoch: float
    expires_at_epoch: float | None = None


class ProviderHealthTransitionSink(Protocol):
    def emit(self, transition: ProviderHealthTransition) -> None: ...


class ProviderHealthAuditSink(Protocol):
    def emit(self, event: ProviderHealthAuditEvent) -> None: ...


class MemoryProviderHealthTransitionSink:
    def __init__(self) -> None:
        self.events: list[ProviderHealthTransition] = []

    def emit(self, transition: ProviderHealthTransition) -> None:
        self.events.append(transition)


class MemoryProviderHealthAuditSink:
    def __init__(self) -> None:
        self.events: list[ProviderHealthAuditEvent] = []

    def emit(self, event: ProviderHealthAuditEvent) -> None:
        self.events.append(event)


_PROVIDER_ATTRIBUTABLE = frozenset(
    {
        "rate_limit",
        "timeout",
        "provider_5xx",
        "capability_temp_unavailable",
        "auth_error",
        "provider_unavailable",
    }
)
_PROVIDER_WIDE = frozenset(
    {
        "rate_limit",
        "timeout",
        "provider_5xx",
        "auth_error",
        "provider_unavailable",
    }
)
_RATE_LIMIT = frozenset({"rate_limit"})
_TIMEOUT = frozenset({"timeout"})


class AdaptiveProviderHealthRegistry:
    """Shared-store-backed operational health and circuit breaker.

    Health is deliberately soft state. Store loss returns UNKNOWN and never blocks business
    correctness. The store is expected to be Redis in a multi-replica deployment and the
    in-memory implementation in deterministic tests.
    """

    def __init__(
        self,
        *,
        store: HealthStateStore,
        policy: ProviderHealthPolicy | None = None,
        clock: HealthClock | None = None,
        policy_resolver: Callable[[str, str | None, str | None], ProviderHealthPolicy]
        | None = None,
        transition_sink: ProviderHealthTransitionSink | None = None,
        audit_sink: ProviderHealthAuditSink | None = None,
    ) -> None:
        self.store = store
        self.default_policy = policy or ProviderHealthPolicy()
        self.clock = clock or SystemHealthClock()
        self.policy_resolver = policy_resolver
        self.transition_sink = transition_sink
        self.audit_sink = audit_sink
        self.store_error_total = 0

    def snapshot(
        self,
        provider: str,
        model: str,
        capability: str | None = None,
    ) -> HealthSnapshot:
        return self.detailed_snapshot(provider, model, capability).to_gateway_snapshot()

    def detailed_snapshot(
        self,
        provider: str,
        model: str | None = None,
        capability: str | None = None,
    ) -> ProviderHealthSnapshot:
        now = self.clock.now()
        try:
            provider_snapshot = self._scope_snapshot(provider, None, None, now)
            endpoint_snapshot = (
                None
                if model is None
                else self._scope_snapshot(provider, model, capability, now)
            )
            override = self._effective_override(provider, model, capability, now)
        except Exception:
            self.store_error_total += 1
            return self._unknown_snapshot(
                provider,
                model,
                capability,
                now,
                reason="health_store_unavailable",
                store_available=False,
            )
        combined = _combine_snapshots(provider_snapshot, endpoint_snapshot)
        if override is None:
            return combined
        mode = ManualOverrideMode(str(override["mode"]))
        reason = str(override["reason"])
        state = (
            ProviderHealthState.DISABLED
            if mode is ManualOverrideMode.DISABLED
            else ProviderHealthState.DEGRADED
        )
        score = 0 if state is ProviderHealthState.DISABLED else min(combined.score, 35)
        return ProviderHealthSnapshot(
            provider=provider,
            model=model,
            capability=capability,
            state=state,
            score=score,
            sample_count=combined.sample_count,
            success_rate=combined.success_rate,
            failure_rate=combined.failure_rate,
            rate_limit_rate=combined.rate_limit_rate,
            timeout_rate=combined.timeout_rate,
            latency_p50_ms=combined.latency_p50_ms,
            latency_p95_ms=combined.latency_p95_ms,
            consecutive_failures=combined.consecutive_failures,
            open_until_epoch=combined.open_until_epoch,
            recovering_inflight=combined.recovering_inflight,
            recovering_successes=combined.recovering_successes,
            capacity_hint=combined.capacity_hint,
            updated_at_epoch=max(combined.updated_at_epoch, float(override["updated_at"])),
            reason=f"manual_{mode.value}:{reason}",
            store_available=combined.store_available,
        )

    def record_success(
        self,
        provider: str,
        model: str,
        latency_ms: int | None,
        *,
        capability: str | None = None,
    ) -> None:
        latency = 0 if latency_ms is None else latency_ms
        if latency < 0:
            raise ValueError("PROVIDER_HEALTH_LATENCY_NEGATIVE")
        self._record(provider, None, None, True, latency, None, None)
        self._record(provider, model, capability, True, latency, None, None)

    def record_failure(
        self,
        provider: str,
        model: str,
        category: str,
        *,
        capability: str | None = None,
        latency_ms: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        normalized = category.strip().lower()
        if normalized not in _PROVIDER_ATTRIBUTABLE:
            return
        latency = 0 if latency_ms is None else latency_ms
        if latency < 0:
            raise ValueError("PROVIDER_HEALTH_LATENCY_NEGATIVE")
        if retry_after_seconds is not None and retry_after_seconds < 0:
            raise ValueError("PROVIDER_HEALTH_RETRY_AFTER_INVALID")
        if normalized in _PROVIDER_WIDE:
            self._record(
                provider,
                None,
                None,
                False,
                latency,
                normalized,
                retry_after_seconds,
            )
        self._record(
            provider,
            model,
            capability,
            False,
            latency,
            normalized,
            retry_after_seconds,
        )

    def record_capacity_hint(
        self,
        provider: str,
        model: str,
        hint: CapacityHint,
        *,
        capability: str | None = None,
    ) -> None:
        now = self.clock.now()
        for scope_model, scope_capability in ((None, None), (model, capability)):
            key = _state_key(provider, scope_model, scope_capability)
            policy = self._policy(provider, scope_model, scope_capability)
            try:
                self.store.atomic_update(
                    key,
                    ttl_seconds=policy.state_ttl_seconds,
                    mutator=lambda raw, now=now, hint=hint: _apply_capacity_hint(raw, now, hint),
                )
            except Exception:
                self.store_error_total += 1

    def acquire_probe(
        self,
        provider: str,
        model: str,
        *,
        capability: str | None = None,
    ) -> bool:
        now = self.clock.now()
        keys = (
            _state_key(provider, None, None),
            _state_key(provider, model, capability),
        )
        acquired: list[str] = []
        try:
            for key, scope_model, scope_capability in (
                (keys[0], None, None),
                (keys[1], model, capability),
            ):
                policy = self._policy(provider, scope_model, scope_capability)
                result = self.store.atomic_update(
                    key,
                    ttl_seconds=policy.state_ttl_seconds,
                    mutator=lambda raw, now=now, policy=policy: _acquire_probe(raw, now, policy),
                )
                current = result.current
                if current is not None and current.get("probe_denied") is True:
                    for acquired_key in acquired:
                        self._release_probe_key(acquired_key, policy)
                    return False
                if current is not None and current.get("probe_acquired") is True:
                    acquired.append(key)
            return True
        except Exception:
            self.store_error_total += 1
            return True

    def release_probe(
        self,
        provider: str,
        model: str,
        *,
        capability: str | None = None,
    ) -> None:
        for key, scope_model, scope_capability in (
            (_state_key(provider, None, None), None, None),
            (_state_key(provider, model, capability), model, capability),
        ):
            self._release_probe_key(key, self._policy(provider, scope_model, scope_capability))

    def disable(
        self,
        provider: str,
        *,
        actor_id: str,
        reason: str,
        ttl_seconds: float,
        model: str | None = None,
        capability: str | None = None,
    ) -> None:
        self._set_override(
            ManualOverrideMode.DISABLED,
            provider,
            actor_id=actor_id,
            reason=reason,
            ttl_seconds=ttl_seconds,
            model=model,
            capability=capability,
        )

    def force_degraded(
        self,
        provider: str,
        *,
        actor_id: str,
        reason: str,
        ttl_seconds: float,
        model: str | None = None,
        capability: str | None = None,
    ) -> None:
        self._set_override(
            ManualOverrideMode.DEGRADED,
            provider,
            actor_id=actor_id,
            reason=reason,
            ttl_seconds=ttl_seconds,
            model=model,
            capability=capability,
        )

    def clear_override(
        self,
        provider: str,
        *,
        actor_id: str,
        reason: str,
        model: str | None = None,
        capability: str | None = None,
    ) -> None:
        self._require_audit(actor_id, reason)
        self.store.delete(_override_key(provider, model, capability))
        self._emit_audit(
            "clear_override",
            provider,
            model,
            capability,
            actor_id,
            reason,
            None,
        )

    def clear_breaker(
        self,
        provider: str,
        *,
        actor_id: str,
        reason: str,
        model: str | None = None,
        capability: str | None = None,
    ) -> None:
        self._require_audit(actor_id, reason)
        self.store.delete(_state_key(provider, model, capability))
        self._emit_audit(
            "clear_breaker",
            provider,
            model,
            capability,
            actor_id,
            reason,
            None,
        )

    def _record(
        self,
        provider: str,
        model: str | None,
        capability: str | None,
        success: bool,
        latency_ms: int,
        category: str | None,
        retry_after_seconds: float | None,
    ) -> None:
        now = self.clock.now()
        policy = self._policy(provider, model, capability)
        key = _state_key(provider, model, capability)
        try:
            result = self.store.atomic_update(
                key,
                ttl_seconds=policy.state_ttl_seconds,
                mutator=lambda raw: _apply_observation(
                    raw,
                    now=now,
                    policy=policy,
                    success=success,
                    latency_ms=latency_ms,
                    category=category,
                    retry_after_seconds=retry_after_seconds,
                ),
            )
        except Exception:
            self.store_error_total += 1
            return
        self._emit_transition_if_changed(
            provider,
            model,
            capability,
            result.previous,
            result.current,
            now,
        )

    def _scope_snapshot(
        self,
        provider: str,
        model: str | None,
        capability: str | None,
        now: float,
    ) -> ProviderHealthSnapshot:
        policy = self._policy(provider, model, capability)
        key = _state_key(provider, model, capability)
        result = self.store.atomic_update(
            key,
            ttl_seconds=policy.state_ttl_seconds,
            mutator=lambda raw: _refresh_record(raw, now, policy),
        )
        if result.current is None:
            return self._unknown_snapshot(provider, model, capability, now)
        self._emit_transition_if_changed(
            provider,
            model,
            capability,
            result.previous,
            result.current,
            now,
        )
        return _snapshot_from_record(
            provider,
            model,
            capability,
            result.current,
            policy,
        )

    def _effective_override(
        self,
        provider: str,
        model: str | None,
        capability: str | None,
        now: float,
    ) -> dict[str, Any] | None:
        endpoint = None
        if model is not None:
            endpoint = self.store.read(_override_key(provider, model, capability))
        provider_override = self.store.read(_override_key(provider, None, None))
        candidates = [item for item in (provider_override, endpoint) if item is not None]
        live = [item for item in candidates if float(item["expires_at"]) > now]
        if not live:
            return None
        return max(live, key=lambda item: float(item["updated_at"]))

    def _set_override(
        self,
        mode: ManualOverrideMode,
        provider: str,
        *,
        actor_id: str,
        reason: str,
        ttl_seconds: float,
        model: str | None,
        capability: str | None,
    ) -> None:
        self._require_audit(actor_id, reason)
        if ttl_seconds <= 0 or ttl_seconds > 7 * 24 * 3600:
            raise ValueError("PROVIDER_HEALTH_OVERRIDE_TTL_INVALID")
        now = self.clock.now()
        expires = now + ttl_seconds
        payload: dict[str, Any] = {
            "mode": mode.value,
            "actor_id": actor_id,
            "reason": reason,
            "updated_at": now,
            "expires_at": expires,
        }
        self.store.atomic_update(
            _override_key(provider, model, capability),
            ttl_seconds=ttl_seconds,
            mutator=lambda _: payload,
        )
        self._emit_audit(
            f"force_{mode.value}",
            provider,
            model,
            capability,
            actor_id,
            reason,
            expires,
        )

    def _release_probe_key(self, key: str, policy: ProviderHealthPolicy) -> None:
        try:
            self.store.atomic_update(
                key,
                ttl_seconds=policy.state_ttl_seconds,
                mutator=_release_probe,
            )
        except Exception:
            self.store_error_total += 1

    def _policy(
        self,
        provider: str,
        model: str | None,
        capability: str | None,
    ) -> ProviderHealthPolicy:
        if self.policy_resolver is None:
            return self.default_policy
        return self.policy_resolver(provider, model, capability)

    def _unknown_snapshot(
        self,
        provider: str,
        model: str | None,
        capability: str | None,
        now: float,
        *,
        reason: str = "no_recent_health_evidence",
        store_available: bool = True,
    ) -> ProviderHealthSnapshot:
        policy = self._policy(provider, model, capability)
        return ProviderHealthSnapshot(
            provider=provider,
            model=model,
            capability=capability,
            state=ProviderHealthState.UNKNOWN,
            score=policy.unknown_score,
            sample_count=0,
            success_rate=0.0,
            failure_rate=0.0,
            rate_limit_rate=0.0,
            timeout_rate=0.0,
            latency_p50_ms=None,
            latency_p95_ms=None,
            consecutive_failures=0,
            open_until_epoch=None,
            recovering_inflight=0,
            recovering_successes=0,
            capacity_hint=None,
            updated_at_epoch=now,
            reason=reason,
            store_available=store_available,
        )

    def _emit_transition_if_changed(
        self,
        provider: str,
        model: str | None,
        capability: str | None,
        previous: dict[str, Any] | None,
        current: dict[str, Any] | None,
        now: float,
    ) -> None:
        if self.transition_sink is None or current is None:
            return
        previous_state = (
            ProviderHealthState.UNKNOWN
            if previous is None
            else ProviderHealthState(str(previous.get("state", "unknown")))
        )
        current_state = ProviderHealthState(str(current.get("state", "unknown")))
        if previous_state is current_state:
            return
        snapshot = _snapshot_from_record(
            provider,
            model,
            capability,
            current,
            self._policy(provider, model, capability),
        )
        self.transition_sink.emit(
            ProviderHealthTransition(
                provider=provider,
                model=model,
                capability=capability,
                previous_state=previous_state,
                current_state=current_state,
                score=snapshot.score,
                sample_count=snapshot.sample_count,
                failure_rate=snapshot.failure_rate,
                latency_p95_ms=snapshot.latency_p95_ms,
                observed_at_epoch=now,
                reason=snapshot.reason,
            )
        )

    def _require_audit(self, actor_id: str, reason: str) -> None:
        if self.audit_sink is None:
            raise RuntimeError("PROVIDER_HEALTH_MANUAL_OVERRIDE_AUDIT_REQUIRED")
        if not actor_id.strip() or not reason.strip():
            raise ValueError("PROVIDER_HEALTH_MANUAL_OVERRIDE_REASON_REQUIRED")

    def _emit_audit(
        self,
        action: str,
        provider: str,
        model: str | None,
        capability: str | None,
        actor_id: str,
        reason: str,
        expires_at: float | None,
    ) -> None:
        assert self.audit_sink is not None
        self.audit_sink.emit(
            ProviderHealthAuditEvent(
                action=action,
                provider=provider,
                model=model,
                capability=capability,
                actor_id=actor_id,
                reason=reason,
                observed_at_epoch=self.clock.now(),
                expires_at_epoch=expires_at,
            )
        )


def _default_record(now: float) -> dict[str, Any]:
    return {
        "state": ProviderHealthState.UNKNOWN.value,
        "samples": [],
        "consecutive_failures": 0,
        "open_until": None,
        "recovering_inflight": 0,
        "recovering_successes": 0,
        "capacity_hint": None,
        "updated_at": now,
    }


def _refresh_record(
    raw: dict[str, Any] | None,
    now: float,
    policy: ProviderHealthPolicy,
) -> dict[str, Any] | None:
    if raw is None:
        return None
    record = raw
    _prune(record, now, policy)
    state = ProviderHealthState(str(record.get("state", "unknown")))
    open_until = record.get("open_until")
    if (
        state is ProviderHealthState.OPEN_CIRCUIT
        and open_until is not None
        and now >= float(open_until)
    ):
        record["state"] = ProviderHealthState.RECOVERING.value
        record["open_until"] = None
        record["recovering_inflight"] = 0
        record["recovering_successes"] = 0
        record["updated_at"] = now
    return record


def _apply_observation(
    raw: dict[str, Any] | None,
    *,
    now: float,
    policy: ProviderHealthPolicy,
    success: bool,
    latency_ms: int,
    category: str | None,
    retry_after_seconds: float | None,
) -> dict[str, Any]:
    record = _default_record(now) if raw is None else raw
    refreshed = _refresh_record(record, now, policy)
    assert refreshed is not None
    record = refreshed
    samples = list(record.get("samples", []))
    samples.append(
        {
            "at": now,
            "success": success,
            "latency_ms": latency_ms,
            "category": category,
        }
    )
    record["samples"] = samples
    _prune(record, now, policy)
    while len(record["samples"]) > policy.max_samples:
        record["samples"].pop(0)

    state = ProviderHealthState(str(record.get("state", "unknown")))
    if success:
        record["consecutive_failures"] = 0
        if state is ProviderHealthState.RECOVERING:
            record["recovering_inflight"] = max(
                0,
                int(record.get("recovering_inflight", 0)) - 1,
            )
            record["recovering_successes"] = int(record.get("recovering_successes", 0)) + 1
            if int(record["recovering_successes"]) >= policy.recovering_successes_to_close:
                _close_record(record, now)
                return record
    else:
        record["consecutive_failures"] = int(record.get("consecutive_failures", 0)) + 1
        if state is ProviderHealthState.RECOVERING:
            record["recovering_inflight"] = max(
                0,
                int(record.get("recovering_inflight", 0)) - 1,
            )
            _open_record(record, now, policy, retry_after_seconds)
            return record
        if category in _RATE_LIMIT and retry_after_seconds and retry_after_seconds > 0:
            _open_record(record, now, policy, retry_after_seconds)
            return record

    _evaluate_record(record, now, policy)
    record["updated_at"] = now
    return record


def _evaluate_record(record: dict[str, Any], now: float, policy: ProviderHealthPolicy) -> None:
    state = ProviderHealthState(str(record.get("state", "unknown")))
    if state in {ProviderHealthState.OPEN_CIRCUIT, ProviderHealthState.RECOVERING}:
        return
    metrics = _metrics(record)
    if int(record.get("consecutive_failures", 0)) >= policy.consecutive_failures_open:
        _open_record(record, now, policy, None)
        return
    if metrics["sample_count"] >= policy.minimum_samples and (
        metrics["failure_rate"] >= policy.open_failure_rate
        or metrics["rate_limit_rate"] >= policy.open_rate_limit_rate
        or metrics["timeout_rate"] >= policy.open_timeout_rate
    ):
        _open_record(record, now, policy, None)
        return
    degraded = metrics["sample_count"] >= policy.minimum_samples and (
        metrics["failure_rate"] >= policy.degraded_failure_rate
        or metrics["rate_limit_rate"] >= policy.degraded_rate_limit_rate
        or metrics["timeout_rate"] >= policy.degraded_timeout_rate
    )
    if metrics["latency_p95_ms"] is not None:
        degraded = degraded or metrics["latency_p95_ms"] >= policy.degraded_latency_p95_ms
    record["state"] = (
        ProviderHealthState.DEGRADED.value if degraded else ProviderHealthState.HEALTHY.value
    )


def _open_record(
    record: dict[str, Any],
    now: float,
    policy: ProviderHealthPolicy,
    retry_after_seconds: float | None,
) -> None:
    cooldown = max(policy.open_cooldown_seconds, retry_after_seconds or 0.0)
    record["state"] = ProviderHealthState.OPEN_CIRCUIT.value
    record["open_until"] = now + cooldown
    record["recovering_inflight"] = 0
    record["recovering_successes"] = 0
    record["updated_at"] = now


def _close_record(record: dict[str, Any], now: float) -> None:
    record["state"] = ProviderHealthState.HEALTHY.value
    record["samples"] = []
    record["consecutive_failures"] = 0
    record["open_until"] = None
    record["recovering_inflight"] = 0
    record["recovering_successes"] = 0
    record["updated_at"] = now


def _acquire_probe(
    raw: dict[str, Any] | None,
    now: float,
    policy: ProviderHealthPolicy,
) -> dict[str, Any] | None:
    refreshed = _refresh_record(raw, now, policy)
    if refreshed is None:
        return None
    state = ProviderHealthState(str(refreshed.get("state", "unknown")))
    refreshed.pop("probe_denied", None)
    refreshed.pop("probe_acquired", None)
    if state is ProviderHealthState.OPEN_CIRCUIT:
        refreshed["probe_denied"] = True
        return refreshed
    if state is not ProviderHealthState.RECOVERING:
        return refreshed
    inflight = int(refreshed.get("recovering_inflight", 0))
    if inflight >= policy.recovering_max_probes:
        refreshed["probe_denied"] = True
        return refreshed
    refreshed["recovering_inflight"] = inflight + 1
    refreshed["probe_acquired"] = True
    refreshed["updated_at"] = now
    return refreshed


def _release_probe(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    raw["recovering_inflight"] = max(0, int(raw.get("recovering_inflight", 0)) - 1)
    raw.pop("probe_denied", None)
    raw.pop("probe_acquired", None)
    return raw


def _apply_capacity_hint(
    raw: dict[str, Any] | None,
    now: float,
    hint: CapacityHint,
) -> dict[str, Any]:
    record = _default_record(now) if raw is None else raw
    record["capacity_hint"] = {
        "remaining": hint.remaining,
        "limit": hint.limit,
        "reset_at_epoch": hint.reset_at_epoch,
        "retry_after_seconds": hint.retry_after_seconds,
    }
    record["updated_at"] = now
    return record


def _prune(record: dict[str, Any], now: float, policy: ProviderHealthPolicy) -> None:
    cutoff = now - policy.window_seconds
    samples = [
        item
        for item in list(record.get("samples", []))
        if float(item["at"]) >= cutoff
    ]
    record["samples"] = samples[-policy.max_samples :]


def _metrics(record: dict[str, Any]) -> dict[str, Any]:
    samples = list(record.get("samples", []))
    count = len(samples)
    failures = [item for item in samples if not bool(item["success"])]
    successes = [item for item in samples if bool(item["success"])]
    rate_limits = [item for item in failures if item.get("category") in _RATE_LIMIT]
    timeouts = [item for item in failures if item.get("category") in _TIMEOUT]
    latencies = [int(item["latency_ms"]) for item in successes if int(item["latency_ms"]) >= 0]
    return {
        "sample_count": count,
        "success_rate": len(successes) / count if count else 0.0,
        "failure_rate": len(failures) / count if count else 0.0,
        "rate_limit_rate": len(rate_limits) / count if count else 0.0,
        "timeout_rate": len(timeouts) / count if count else 0.0,
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
    }


def _snapshot_from_record(
    provider: str,
    model: str | None,
    capability: str | None,
    record: dict[str, Any],
    policy: ProviderHealthPolicy,
) -> ProviderHealthSnapshot:
    metrics = _metrics(record)
    state = ProviderHealthState(str(record.get("state", "unknown")))
    score = _score(state, metrics, policy)
    hint_payload = record.get("capacity_hint")
    hint = None
    if isinstance(hint_payload, dict):
        hint = CapacityHint(
            remaining=hint_payload.get("remaining"),
            limit=hint_payload.get("limit"),
            reset_at_epoch=hint_payload.get("reset_at_epoch"),
            retry_after_seconds=hint_payload.get("retry_after_seconds"),
        )
    reason = _reason(state, metrics, policy)
    return ProviderHealthSnapshot(
        provider=provider,
        model=model,
        capability=capability,
        state=state,
        score=score,
        sample_count=int(metrics["sample_count"]),
        success_rate=float(metrics["success_rate"]),
        failure_rate=float(metrics["failure_rate"]),
        rate_limit_rate=float(metrics["rate_limit_rate"]),
        timeout_rate=float(metrics["timeout_rate"]),
        latency_p50_ms=metrics["latency_p50_ms"],
        latency_p95_ms=metrics["latency_p95_ms"],
        consecutive_failures=int(record.get("consecutive_failures", 0)),
        open_until_epoch=(
            None if record.get("open_until") is None else float(record["open_until"])
        ),
        recovering_inflight=int(record.get("recovering_inflight", 0)),
        recovering_successes=int(record.get("recovering_successes", 0)),
        capacity_hint=hint,
        updated_at_epoch=float(record.get("updated_at", 0.0)),
        reason=reason,
    )


def _combine_snapshots(
    provider_snapshot: ProviderHealthSnapshot,
    endpoint_snapshot: ProviderHealthSnapshot | None,
) -> ProviderHealthSnapshot:
    if endpoint_snapshot is None:
        return provider_snapshot
    severity = {
        ProviderHealthState.DISABLED: 6,
        ProviderHealthState.OPEN_CIRCUIT: 5,
        ProviderHealthState.RECOVERING: 4,
        ProviderHealthState.DEGRADED: 3,
        ProviderHealthState.UNKNOWN: 2,
        ProviderHealthState.HEALTHY: 1,
    }
    selected = max((provider_snapshot, endpoint_snapshot), key=lambda item: severity[item.state])
    return ProviderHealthSnapshot(
        provider=endpoint_snapshot.provider,
        model=endpoint_snapshot.model,
        capability=endpoint_snapshot.capability,
        state=selected.state,
        score=min(provider_snapshot.score, endpoint_snapshot.score),
        sample_count=endpoint_snapshot.sample_count,
        success_rate=endpoint_snapshot.success_rate,
        failure_rate=endpoint_snapshot.failure_rate,
        rate_limit_rate=endpoint_snapshot.rate_limit_rate,
        timeout_rate=endpoint_snapshot.timeout_rate,
        latency_p50_ms=endpoint_snapshot.latency_p50_ms,
        latency_p95_ms=endpoint_snapshot.latency_p95_ms,
        consecutive_failures=max(
            provider_snapshot.consecutive_failures,
            endpoint_snapshot.consecutive_failures,
        ),
        open_until_epoch=selected.open_until_epoch,
        recovering_inflight=selected.recovering_inflight,
        recovering_successes=selected.recovering_successes,
        capacity_hint=endpoint_snapshot.capacity_hint or provider_snapshot.capacity_hint,
        updated_at_epoch=max(
            provider_snapshot.updated_at_epoch,
            endpoint_snapshot.updated_at_epoch,
        ),
        reason=f"combined:{selected.reason}",
        store_available=provider_snapshot.store_available and endpoint_snapshot.store_available,
    )


def _score(
    state: ProviderHealthState,
    metrics: dict[str, Any],
    policy: ProviderHealthPolicy,
) -> int:
    if state in {ProviderHealthState.OPEN_CIRCUIT, ProviderHealthState.DISABLED}:
        return 0
    if state is ProviderHealthState.RECOVERING:
        return policy.recovering_score
    if state is ProviderHealthState.UNKNOWN:
        return policy.unknown_score
    penalty = round(float(metrics["failure_rate"]) * 65)
    p95 = metrics["latency_p95_ms"]
    if p95 is not None and p95 > policy.degraded_latency_p95_ms:
        penalty += min(25, round((p95 / policy.degraded_latency_p95_ms - 1) * 20))
    score = max(1, 100 - penalty)
    if state is ProviderHealthState.DEGRADED:
        score = min(score, 65)
    return min(100, score)


def _reason(
    state: ProviderHealthState,
    metrics: dict[str, Any],
    policy: ProviderHealthPolicy,
) -> str:
    if state is ProviderHealthState.OPEN_CIRCUIT:
        return "circuit_open"
    if state is ProviderHealthState.RECOVERING:
        return "half_open_recovery"
    if state is ProviderHealthState.UNKNOWN:
        return "no_recent_health_evidence"
    if state is ProviderHealthState.DEGRADED:
        if float(metrics["failure_rate"]) >= policy.degraded_failure_rate:
            return "failure_rate_degraded"
        if metrics["latency_p95_ms"] is not None and metrics["latency_p95_ms"] >= policy.degraded_latency_p95_ms:
            return "latency_p95_degraded"
        if float(metrics["rate_limit_rate"]) >= policy.degraded_rate_limit_rate:
            return "rate_limit_degraded"
        if float(metrics["timeout_rate"]) >= policy.degraded_timeout_rate:
            return "timeout_degraded"
    return "healthy"


def _state_key(provider: str, model: str | None, capability: str | None) -> str:
    _validate_identity(provider, model, capability)
    scope = "provider" if model is None else "endpoint"
    raw = f"{scope}|{provider}|{model or '*'}|{capability or '*'}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"state:{scope}:{digest}"


def _override_key(provider: str, model: str | None, capability: str | None) -> str:
    _validate_identity(provider, model, capability)
    scope = "provider" if model is None else "endpoint"
    raw = f"override|{scope}|{provider}|{model or '*'}|{capability or '*'}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"override:{scope}:{digest}"


def _validate_identity(provider: str, model: str | None, capability: str | None) -> None:
    if not provider.strip():
        raise ValueError("PROVIDER_HEALTH_PROVIDER_INVALID")
    if model is None and capability is not None:
        raise ValueError("PROVIDER_HEALTH_CAPABILITY_REQUIRES_MODEL")
    if model is not None and not model.strip():
        raise ValueError("PROVIDER_HEALTH_MODEL_INVALID")


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]
