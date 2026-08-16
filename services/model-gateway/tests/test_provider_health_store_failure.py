from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lumi_model_gateway.provider_health import (
    AdaptiveProviderHealthRegistry,
    ProviderHealthState,
)
from lumi_model_gateway.provider_health_store import AtomicStateUpdate


class FailingHealthStateStore:
    def read(self, key: str) -> dict[str, Any] | None:
        del key
        raise ConnectionError("redis unavailable")

    def atomic_update(
        self,
        key: str,
        *,
        ttl_seconds: float,
        mutator: Callable[
            [dict[str, Any] | None],
            dict[str, Any] | None,
        ],
    ) -> AtomicStateUpdate:
        del key, ttl_seconds, mutator
        raise ConnectionError("redis unavailable")

    def delete(self, key: str) -> None:
        del key
        raise ConnectionError("redis unavailable")


def test_store_failure_returns_unknown_and_never_synthetic_healthy() -> None:
    health = AdaptiveProviderHealthRegistry(
        store=FailingHealthStateStore(),
    )
    snapshot = health.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert snapshot.state is ProviderHealthState.UNKNOWN
    assert snapshot.store_available is False
    assert snapshot.reason == "health_store_unavailable"
    assert 0 < snapshot.score < 100
    assert health.store_error_total == 1


def test_store_failure_does_not_make_operational_health_business_truth() -> None:
    health = AdaptiveProviderHealthRegistry(
        store=FailingHealthStateStore(),
    )
    assert health.acquire_probe(
        "provider-a",
        "model-a",
        capability="llm.reasoning",
    )
    assert health.store_error_total >= 1
