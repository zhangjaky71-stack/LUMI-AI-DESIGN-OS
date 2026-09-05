from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_model_gateway import (
    Capability,
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    MockProvider,
    ModelRequest,
    NoRouteError,
)
from lumi_model_gateway.profile_routing import ModelProfileRouter


class ModelProfileRoutingTests(unittest.IsolatedAsyncioTestCase):
    def _router(self) -> ModelProfileRouter:
        registry = InMemoryProviderRegistry()
        registry.register(MockProvider(provider="mock", model="fast", quality_score=70))
        registry.register(MockProvider(provider="mock", model="high", quality_score=95))
        return ModelProfileRouter(
            registry=registry,
            health=InMemoryProviderHealthRegistry(),
            profile_routes={
                "reasoning.fast": frozenset({"mock:fast"}),
                "reasoning.high": frozenset({"mock:high"}),
            },
        )

    async def test_profile_is_a_hard_provider_model_constraint(self) -> None:
        router = self._router()
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_REASONING,
            inputs={"prompt": "hello"},
            constraints={"model_profile": "reasoning.fast"},
        )
        decision = await router.route(request)
        self.assertEqual(decision.candidates[0].provider, "mock")
        self.assertEqual(decision.candidates[0].model, "fast")
        self.assertEqual(len(decision.candidates), 1)
        self.assertIn("MODEL_PROFILE_MATCH", decision.candidates[0].reason_codes)
        self.assertEqual(
            decision.rejected["mock:high"],
            ("MODEL_PROFILE_MISMATCH",),
        )

    async def test_unknown_profile_fails_closed(self) -> None:
        router = self._router()
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_REASONING,
            inputs={"prompt": "hello"},
            constraints={"model_profile": "reasoning.missing"},
        )
        with self.assertRaises(NoRouteError):
            await router.route(request)

    async def test_invalid_profile_is_rejected_before_routing(self) -> None:
        router = self._router()
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_REASONING,
            inputs={"prompt": "hello"},
            constraints={"model_profile": "bad profile"},
        )
        with self.assertRaises(ValueError):
            await router.route(request)


if __name__ == "__main__":
    unittest.main()
