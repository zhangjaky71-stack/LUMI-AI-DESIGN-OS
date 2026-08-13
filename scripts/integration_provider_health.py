from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from lumi_model_gateway import (
    Capability,
    InMemoryCapabilityRegistry,
    InMemoryProviderRegistry,
    MockProvider,
    ModelRequest,
    RegistryAwareModelRouter,
    compile_registry_seed,
)
from lumi_model_gateway.provider_health import (
    AdaptiveProviderHealthRegistry,
    ProviderHealthPolicy,
    ProviderHealthState,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "config/model-registry/registry.seed.v1.yaml"


async def main_async() -> None:
    snapshot = compile_registry_seed(SEED, repository_root=ROOT)
    reasoning = snapshot.list_models(Capability.LLM_REASONING)
    by_provider: dict[str, object] = {}
    for model in reasoning:
        by_provider.setdefault(model.provider, model)
    selected = list(by_provider.values())[:2]
    if len(selected) != 2:
        raise AssertionError("NODE-24 integration requires two reasoning providers")

    first = selected[0]
    second = selected[1]
    first_provider = getattr(first, "provider")
    first_model = getattr(first, "model")
    second_provider = getattr(second, "provider")
    second_model = getattr(second, "model")

    adapters = (
        MockProvider(provider=first_provider, model=first_model, quality_score=100),
        MockProvider(provider=second_provider, model=second_model, quality_score=1),
    )
    health = AdaptiveProviderHealthRegistry(
        policy=ProviderHealthPolicy(
            minimum_samples=3,
            consecutive_failures_open=3,
            open_failure_rate=0.50,
        )
    )
    for _ in range(3):
        health.record_failure(
            first_provider,
            first_model,
            error_category="provider_503",
        )
    first_health = health.snapshot(first_provider, first_model)
    assert first_health.state == ProviderHealthState.OPEN
    assert first_health.score == 0

    router = RegistryAwareModelRouter(
        registry=InMemoryProviderRegistry(adapters),
        health=health,
        capability_registry=InMemoryCapabilityRegistry(snapshot),
    )
    request = ModelRequest(
        organization_id=uuid4(),
        operation_id=uuid4(),
        capability=Capability.LLM_REASONING,
        inputs={"prompt": "route around open provider"},
    )
    decision = await router.route(request)
    routed = {(item.provider, item.model) for item in decision.candidates}
    assert (first_provider, first_model) not in routed, decision
    assert decision.candidates[0].provider == second_provider
    assert decision.candidates[0].model == second_model


def main() -> int:
    asyncio.run(main_async())
    print("NODE-24 provider health routing integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
