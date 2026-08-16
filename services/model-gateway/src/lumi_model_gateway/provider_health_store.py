from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

JsonObject = dict[str, Any]
StateMutator = Callable[[JsonObject | None], JsonObject | None]


@dataclass(frozen=True, slots=True)
class AtomicStateUpdate:
    previous: JsonObject | None
    current: JsonObject | None


class HealthStateStore(Protocol):
    """Short-lived operational state only; never business truth."""

    def read(self, key: str) -> JsonObject | None: ...

    def atomic_update(
        self,
        key: str,
        *,
        ttl_seconds: float,
        mutator: StateMutator,
    ) -> AtomicStateUpdate: ...

    def delete(self, key: str) -> None: ...


class MemoryHealthStateStore:
    """Deterministic reference store for tests and single-process development."""

    def __init__(self, *, now: Callable[[], float]) -> None:
        self._now = now
        self._values: dict[str, tuple[float, JsonObject]] = {}
        self._lock = threading.RLock()

    def read(self, key: str) -> JsonObject | None:
        with self._lock:
            self._expire(key)
            item = self._values.get(key)
            return None if item is None else _copy_json(item[1])

    def atomic_update(
        self,
        key: str,
        *,
        ttl_seconds: float,
        mutator: StateMutator,
    ) -> AtomicStateUpdate:
        if ttl_seconds <= 0:
            raise ValueError("PROVIDER_HEALTH_STORE_TTL_INVALID")
        with self._lock:
            self._expire(key)
            item = self._values.get(key)
            previous = None if item is None else _copy_json(item[1])
            current = mutator(
                None if previous is None else _copy_json(previous)
            )
            if current is None:
                self._values.pop(key, None)
                return AtomicStateUpdate(previous, None)
            serializable = _copy_json(current)
            effective_ttl = _effective_ttl_seconds(
                serializable,
                ttl_seconds,
            )
            self._values[key] = (
                self._now() + effective_ttl,
                serializable,
            )
            return AtomicStateUpdate(
                previous,
                _copy_json(serializable),
            )

    def delete(self, key: str) -> None:
        with self._lock:
            self._values.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()

    def _expire(self, key: str) -> None:
        item = self._values.get(key)
        if item is not None and self._now() >= item[0]:
            self._values.pop(key, None)


class RedisClientLike(Protocol):
    def get(self, name: str) -> bytes | str | None: ...

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
    ) -> object: ...

    def delete(self, *names: str) -> int: ...

    def lock(
        self,
        name: str,
        *,
        timeout: float,
        blocking_timeout: float,
    ) -> Any: ...


class RedisHealthStateStore:
    """redis-py-compatible shared operational store with injected client.

    The caller owns client construction, authentication, TLS and pooling. A
    distributed per-key lock makes each Python load/modify/save mutation atomic
    across Gateway replicas. Redis failure is handled by the registry as UNKNOWN;
    this store is never used for financial, idempotency or provenance truth.
    """

    def __init__(
        self,
        client: RedisClientLike,
        *,
        prefix: str = "lumi:provider-health:v1",
        lock_timeout_seconds: float = 5.0,
        blocking_timeout_seconds: float = 2.0,
    ) -> None:
        if not prefix:
            raise ValueError("PROVIDER_HEALTH_REDIS_PREFIX_INVALID")
        if (
            lock_timeout_seconds <= 0
            or blocking_timeout_seconds <= 0
        ):
            raise ValueError("PROVIDER_HEALTH_REDIS_LOCK_INVALID")
        self.client = client
        self.prefix = prefix.rstrip(":")
        self.lock_timeout_seconds = lock_timeout_seconds
        self.blocking_timeout_seconds = blocking_timeout_seconds

    def read(self, key: str) -> JsonObject | None:
        raw = self.client.get(self._key(key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("PROVIDER_HEALTH_REDIS_PAYLOAD_INVALID")
        return payload

    def atomic_update(
        self,
        key: str,
        *,
        ttl_seconds: float,
        mutator: StateMutator,
    ) -> AtomicStateUpdate:
        if ttl_seconds <= 0:
            raise ValueError("PROVIDER_HEALTH_STORE_TTL_INVALID")
        redis_key = self._key(key)
        lock = self.client.lock(
            redis_key + ":lock",
            timeout=self.lock_timeout_seconds,
            blocking_timeout=self.blocking_timeout_seconds,
        )
        with lock:
            previous = self.read(key)
            current = mutator(
                None if previous is None else _copy_json(previous)
            )
            if current is None:
                self.client.delete(redis_key)
                return AtomicStateUpdate(previous, None)
            serializable = _copy_json(current)
            encoded = json.dumps(
                serializable,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            effective_ttl = _effective_ttl_seconds(
                serializable,
                ttl_seconds,
            )
            self.client.set(
                redis_key,
                encoded,
                ex=max(1, math.ceil(effective_ttl)),
            )
            return AtomicStateUpdate(
                previous,
                _copy_json(serializable),
            )

    def delete(self, key: str) -> None:
        self.client.delete(self._key(key))

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"


def _effective_ttl_seconds(
    value: JsonObject,
    requested_ttl: float,
) -> float:
    """Keep explicit cooldown/reset/override horizons from expiring early."""

    anchor = value.get("updated_at")
    if not isinstance(anchor, (int, float)):
        return requested_ttl
    horizons: list[float] = []
    for field in ("open_until", "expires_at"):
        candidate = value.get(field)
        if isinstance(candidate, (int, float)):
            horizons.append(float(candidate))
    capacity = value.get("capacity_hint")
    if isinstance(capacity, dict):
        reset_at = capacity.get("reset_at_epoch")
        if isinstance(reset_at, (int, float)):
            horizons.append(float(reset_at))
    required = max(
        (horizon - float(anchor) for horizon in horizons),
        default=0.0,
    )
    return max(requested_ttl, required)


def _copy_json(value: JsonObject) -> JsonObject:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError("health state must be a JSON object")
    return decoded
