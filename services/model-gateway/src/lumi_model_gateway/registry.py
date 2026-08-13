from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .errors import ErrorCategory, ProviderInvocationError
from .ports import ProviderAdapter


class InMemoryProviderRegistry:
    """NODE-22 runtime registry; NODE-23 replaces this with the durable capability registry."""

    def __init__(self, adapters: tuple[ProviderAdapter, ...] = ()) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ProviderAdapter) -> None:
        key = adapter.descriptor.key
        if key in self._adapters:
            raise ValueError(f"MODEL_PROVIDER_DUPLICATE:{key}")
        self._adapters[key] = adapter

    def adapters(self) -> tuple[ProviderAdapter, ...]:
        return tuple(self._adapters[key] for key in sorted(self._adapters))

    def get(self, provider: str, model: str) -> ProviderAdapter:
        key = f"{provider}:{model}"
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise KeyError(f"MODEL_PROVIDER_NOT_FOUND:{key}") from exc


@dataclass(slots=True)
class _HealthState:
    consecutive_failures: int = 0
    unhealthy_until: float = 0.0


class InMemoryProviderHealthRegistry:
    def __init__(
        self,
        *,
        failure_threshold: int = 2,
        cooldown_seconds: float = 30.0,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("MODEL_HEALTH_FAILURE_THRESHOLD_INVALID")
        if cooldown_seconds <= 0:
            raise ValueError("MODEL_HEALTH_COOLDOWN_INVALID")
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._states: dict[str, _HealthState] = {}
        self._lock = threading.Lock()

    def healthy(self, provider: str, model: str) -> bool:
        key = f"{provider}:{model}"
        with self._lock:
            state = self._states.get(key)
            if state is None:
                return True
            return state.unhealthy_until <= time.monotonic()

    def set_unhealthy(
        self,
        provider: str,
        model: str,
        *,
        seconds: float | None = None,
    ) -> None:
        key = f"{provider}:{model}"
        with self._lock:
            state = self._states.setdefault(key, _HealthState())
            state.consecutive_failures = self.failure_threshold
            state.unhealthy_until = time.monotonic() + (
                seconds if seconds is not None else self.cooldown_seconds
            )

    def record_success(self, provider: str, model: str) -> None:
        key = f"{provider}:{model}"
        with self._lock:
            self._states[key] = _HealthState()

    def record_failure(
        self,
        provider: str,
        model: str,
        error: ProviderInvocationError,
    ) -> None:
        if error.category not in {
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.TIMEOUT,
            ErrorCategory.PROVIDER_5XX,
            ErrorCategory.CAPABILITY_TEMP_UNAVAILABLE,
            ErrorCategory.PROVIDER_UNAVAILABLE,
        }:
            return
        key = f"{provider}:{model}"
        with self._lock:
            state = self._states.setdefault(key, _HealthState())
            state.consecutive_failures += 1
            if state.consecutive_failures >= self.failure_threshold:
                state.unhealthy_until = time.monotonic() + self.cooldown_seconds
