from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from lumi_model_gateway import (
    Capability,
    EvidenceConfidence,
    InMemoryCapabilityRegistry,
    InMemoryProviderHealthRegistry,
    InMemoryProviderRegistry,
    MockProvider,
    ModelRequest,
    RegistryAwareModelRouter,
    RegistryOrganizationPolicy,
    SupportLevel,
    compile_registry_seed,
)
from lumi_model_gateway.capability_registry import BenchmarkScore
from lumi_model_gateway.errors import NoRouteError

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "config/model-registry/registry.seed.v1.yaml"


class CapabilityRegistryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.snapshot = compile_registry_seed(SEED, repository_root=ROOT)

    def test_node07_seed_compiles_all_models_without_inventing_benchmarks(self) -> None:
        self.assertEqual(len(self.snapshot.models), 28)
        self.assertEqual(self.snapshot.source_registry_version, "1.0.0")
        self.assertEqual(self.snapshot.benchmarks, ())
        self.assertEqual(
            self.snapshot.support(
                "openai:gpt-image-2",
                Capability.IMAGE_GENERATE,
            ),
            SupportLevel.FULL,
        )
        self.assertEqual(
            self.snapshot.support(
                "openai:gpt-image-2",
                Capability.OCR_DOCUMENT,
            ),
            SupportLevel.UNKNOWN,
        )
        self.assertEqual(
            self.snapshot.support(
                "google:gemini-embedding-2",
                Capability.EMBEDDING_MULTIMODAL,
            ),
            SupportLevel.FULL,
        )
        self.assertEqual(
            self.snapshot.support(
                "runway:aleph2",
                Capability.VIDEO_EDIT,
            ),
            SupportLevel.FULL,
        )
        video_edit_profile = next(
            item
            for item in self.snapshot.routing_profiles
            if item.profile == "video.edit"
        )
        self.assertEqual(
            video_edit_profile.required_capabilities,
            (Capability.VIDEO_EDIT,),
        )

    def test_unknown_and_partial_are_not_treated_as_full(self) -> None:
        key = "openai:gpt-image-2"
        unknown = self.snapshot.list_models(Capability.OCR_DOCUMENT)
        self.assertNotIn(key, {item.model_key for item in unknown})
        existing = self.snapshot.claim(key, Capability.IMAGE_GENERATE)
        assert existing is not None
        partial = replace(existing, support=SupportLevel.PARTIAL)
        claims = tuple(
            partial if item is existing else item
            for item in self.snapshot.capability_claims
        )
        changed = replace(self.snapshot, capability_claims=claims)
        self.assertNotIn(
            key,
            {
                item.model_key
                for item in changed.list_models(Capability.IMAGE_GENERATE)
            },
        )
        self.assertIn(
            key,
            {
                item.model_key
                for item in changed.list_models(
                    Capability.IMAGE_GENERATE,
                    allow_partial=True,
                )
            },
        )

    def test_pricing_is_time_scoped_and_expired_price_is_not_current(self) -> None:
        key = "openai:gpt-5.6-sol"
        active = self.snapshot.pricing_at(
            key,
            datetime(2026, 8, 14, tzinfo=UTC),
        )
        expired = self.snapshot.pricing_at(
            key,
            datetime(2026, 9, 13, tzinfo=UTC),
        )
        self.assertGreater(len(active), 0)
        self.assertEqual(expired, ())
        self.assertTrue(all(item.currency == "USD" for item in active))

    def test_generic_native_usd_prices_are_preserved(self) -> None:
        prices = self.snapshot.pricing_at(
            "runway:gen4.5",
            datetime(2026, 8, 14, tzinfo=UTC),
        )
        self.assertTrue(any(item.unit == "video_second:native" for item in prices))
        self.assertTrue(any(item.price == Decimal("0.12") for item in prices))

    def test_org_policy_filters_provider_without_mutating_global_snapshot(self) -> None:
        organization_id = uuid4()
        policy = RegistryOrganizationPolicy(
            organization_id=organization_id,
            policy_version=1,
            disabled_providers=frozenset({"openai"}),
        )
        scoped = replace(self.snapshot, organization_policies=(policy,))
        models = scoped.list_models(
            Capability.LLM_REASONING,
            organization_id=organization_id,
        )
        self.assertTrue(models)
        self.assertNotIn("openai", {item.provider for item in models})
        self.assertIn(
            "openai",
            {
                item.provider
                for item in self.snapshot.list_models(Capability.LLM_REASONING)
            },
        )

    def test_hard_region_policy_rejects_unknown_region_facts(self) -> None:
        organization_id = uuid4()
        policy = RegistryOrganizationPolicy(
            organization_id=organization_id,
            policy_version=1,
            allowed_regions=frozenset({"jp"}),
        )
        scoped = replace(self.snapshot, organization_policies=(policy,))
        models = scoped.list_models(
            Capability.LLM_REASONING,
            organization_id=organization_id,
        )
        self.assertEqual(models, ())

    def test_benchmark_history_selects_latest_profile_run(self) -> None:
        first = BenchmarkScore(
            model_key="openai:gpt-5.6-sol",
            profile="planning",
            score=Decimal("81.5"),
            dataset_version="planning-v1",
            run_id="run-1",
            sample_count=100,
            statistics_json='{"p50":"81.5"}',
            confidence=EvidenceConfidence.LIVE_TEST,
            observed_at=datetime(2026, 8, 13, 1, tzinfo=UTC),
            source_ref="eval://run-1",
        )
        second = replace(
            first,
            score=Decimal("84.0"),
            run_id="run-2",
            observed_at=datetime(2026, 8, 13, 2, tzinfo=UTC),
        )
        snapshot = replace(self.snapshot, benchmarks=(first, second))
        latest = snapshot.benchmark("openai:gpt-5.6-sol", "planning")
        assert latest is not None
        self.assertEqual(latest.run_id, "run-2")
        self.assertEqual(
            snapshot.quality_score(
                "openai:gpt-5.6-sol",
                Capability.LLM_REASONING,
            ),
            84,
        )

    def test_cache_activation_does_not_mutate_captured_request_snapshot(self) -> None:
        registry = InMemoryCapabilityRegistry(self.snapshot)
        captured = registry.snapshot()
        changed = replace(
            self.snapshot,
            registry_version=2,
            content_hash="f" * 64,
        )
        registry.activate(changed)
        self.assertEqual(captured.registry_version, 1)
        self.assertEqual(registry.snapshot().registry_version, 2)
        self.assertTrue(registry.invalidate(captured.content_hash))

    async def test_router_uses_one_registry_snapshot_and_unknown_blocks_route(self) -> None:
        adapter = MockProvider(
            provider="openai",
            model="gpt-5.6-sol",
            quality_score=99,
        )
        providers = InMemoryProviderRegistry((adapter,))
        health = InMemoryProviderHealthRegistry()
        registry = InMemoryCapabilityRegistry(self.snapshot)
        router = RegistryAwareModelRouter(
            registry=providers,
            health=health,
            capability_registry=registry,
        )
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_REASONING,
            inputs={"prompt": "plan"},
        )
        decision = await router.route(request)
        self.assertEqual(decision.candidates[0].model, "gpt-5.6-sol")
        reasons = decision.candidates[0].reason_codes
        self.assertTrue(
            any(item.startswith("REGISTRY_SNAPSHOT:") for item in reasons)
        )
        self.assertIn("REGISTRY_VERSION:1", reasons)

        claims = tuple(
            item
            for item in self.snapshot.capability_claims
            if not (
                item.model_key == "openai:gpt-5.6-sol"
                and item.capability == Capability.LLM_REASONING
            )
        )
        registry.activate(
            replace(
                self.snapshot,
                registry_version=2,
                content_hash="e" * 64,
                capability_claims=claims,
            )
        )
        with self.assertRaises(NoRouteError):
            await router.route(request)
        self.assertIn("REGISTRY_VERSION:1", reasons)

    async def test_router_rejects_requested_region_when_registry_region_unknown(self) -> None:
        adapter = MockProvider(
            provider="openai",
            model="gpt-5.6-sol",
        )
        router = RegistryAwareModelRouter(
            registry=InMemoryProviderRegistry((adapter,)),
            health=InMemoryProviderHealthRegistry(),
            capability_registry=InMemoryCapabilityRegistry(self.snapshot),
        )
        request = ModelRequest(
            organization_id=uuid4(),
            operation_id=uuid4(),
            capability=Capability.LLM_REASONING,
            inputs={"prompt": "regional"},
            constraints={"region": "jp"},
        )
        with self.assertRaisesRegex(NoRouteError, "REGISTRY_REGION_UNKNOWN"):
            await router.route(request)


if __name__ == "__main__":
    unittest.main()
