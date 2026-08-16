from __future__ import annotations

from dataclasses import dataclass

from lumi_model_gateway.provider_health_store import MemoryHealthStateStore


@dataclass
class ManualClock:
    value: float = 1_700_000_000.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_open_until_extends_operational_ttl() -> None:
    clock = ManualClock()
    store = MemoryHealthStateStore(now=clock.now)
    store.atomic_update(
        "provider-a",
        ttl_seconds=10,
        mutator=lambda _: {
            "state": "open_circuit",
            "updated_at": clock.now(),
            "open_until": clock.now() + 60,
        },
    )
    clock.advance(20)
    assert store.read("provider-a") is not None
    clock.advance(41)
    assert store.read("provider-a") is None


def test_capacity_reset_extends_operational_ttl() -> None:
    clock = ManualClock()
    store = MemoryHealthStateStore(now=clock.now)
    store.atomic_update(
        "provider-a",
        ttl_seconds=10,
        mutator=lambda _: {
            "state": "degraded",
            "updated_at": clock.now(),
            "capacity_hint": {
                "remaining": 0,
                "limit": 10,
                "reset_at_epoch": clock.now() + 90,
                "retry_after_seconds": None,
            },
        },
    )
    clock.advance(30)
    assert store.read("provider-a") is not None
    clock.advance(61)
    assert store.read("provider-a") is None
