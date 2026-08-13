from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-24 contract marker: {needle}")


def main() -> int:
    require(
        "services/model-gateway/src/lumi_model_gateway/provider_health.py",
        'HEALTHY = "healthy"',
        'DEGRADED = "degraded"',
        'OPEN = "open"',
        'HALF_OPEN = "half_open"',
        "window_seconds",
        "consecutive_failures_open",
        "open_cooldown_seconds",
        "half_open_successes_to_close",
        "retry_after_seconds",
        '"invalid_request"',
        "record_telemetry",
        "acquire_probe",
        "latency_p95_ms",
    )
    require(
        "services/model-gateway/src/lumi_model_gateway/provider_health_monitor.py",
        "TelemetryEvent",
        "ProviderHealthTransition",
        "previous_state",
        "current_state",
        "transition_sink.emit",
    )
    require(
        "scripts/integration_provider_health.py",
        "RegistryAwareModelRouter",
        "ProviderHealthState.OPEN",
        "route around open provider",
    )

    from lumi_model_gateway.ports import ProviderHealthRegistry
    from lumi_model_gateway.provider_health import AdaptiveProviderHealthRegistry

    protocol_methods = {
        name
        for name, value in ProviderHealthRegistry.__dict__.items()
        if not name.startswith("_") and callable(value)
    }
    missing = sorted(
        name
        for name in protocol_methods
        if not hasattr(AdaptiveProviderHealthRegistry, name)
    )
    if missing:
        raise SystemExit(
            "AdaptiveProviderHealthRegistry misses ProviderHealthRegistry methods: "
            + ",".join(missing)
        )

    print("NODE-24 provider health static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
