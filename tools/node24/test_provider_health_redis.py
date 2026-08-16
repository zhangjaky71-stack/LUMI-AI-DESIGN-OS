from __future__ import annotations

import argparse
import time
import uuid

from lumi_model_gateway.provider_health import (
    AdaptiveProviderHealthRegistry,
    CapacityHint,
    ProviderHealthPolicy,
    ProviderHealthState,
)
from lumi_model_gateway.provider_health_store import (
    RedisHealthStateStore,
)


def build_registry(
    client: object,
    prefix: str,
) -> AdaptiveProviderHealthRegistry:
    return AdaptiveProviderHealthRegistry(
        store=RedisHealthStateStore(
            client,  # type: ignore[arg-type]
            prefix=prefix,
        ),
        policy=ProviderHealthPolicy(
            minimum_samples=3,
            max_samples=20,
            window_seconds=60,
            state_ttl_seconds=300,
            consecutive_failures_open=3,
            open_cooldown_seconds=30,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    try:
        import redis
    except ImportError as exc:
        raise RuntimeError(
            "redis package is required for NODE-24 integration verification"
        ) from exc

    client = redis.Redis.from_url(
        args.url,
        decode_responses=False,
    )
    assert client.ping() is True
    prefix = f"lumi:node24:test:{uuid.uuid4().hex}"

    first = build_registry(client, prefix)
    second = build_registry(client, prefix)
    for _ in range(3):
        first.record_failure(
            "provider-a",
            "model-a",
            "provider_5xx",
            capability="llm.reasoning",
        )

    shared = second.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert shared.state is ProviderHealthState.OPEN_CIRCUIT
    assert shared.store_available is True
    assert shared.score == 0

    keys = list(client.scan_iter(match=f"{prefix}:*"))
    assert keys
    client.delete(*keys)
    reset = second.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert reset.state is ProviderHealthState.UNKNOWN
    assert reset.routable is True
    assert reset.store_available is True

    second.record_capacity_hint(
        "provider-a",
        "model-a",
        hint=CapacityHint(
            remaining=0,
            limit=100,
            reset_at_epoch=time.time() + 30,
        ),
        capability="llm.reasoning",
    )
    capacity = first.detailed_snapshot(
        "provider-a",
        "model-a",
        "llm.reasoning",
    )
    assert capacity.state is ProviderHealthState.DEGRADED
    assert capacity.reason.endswith("capacity_exhausted")

    keys = list(client.scan_iter(match=f"{prefix}:*"))
    if keys:
        client.delete(*keys)
    print("NODE24_REDIS_HEALTH_VALID")


if __name__ == "__main__":
    main()
