from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from lumi_model_gateway.models import Capability
from lumi_model_gateway.registry import (
    BenchmarkScore,
    CapabilityClaim,
    CapabilityRegistry,
    CapabilitySupport,
    ClaimConfidence,
    ModelLifecycle,
    ModelRecord,
    OrganizationModelPolicy,
    PricingSnapshot,
    RegistrySnapshot,
    RoutingProfile,
    registry_checksum,
)
from lumi_model_gateway.registry_seed import load_seed_snapshot

ROOT = Path(__file__).resolve().parents[3]
ORG = UUID("01910000-0000-7000-8000-000000000501")
NOW = datetime(2026, 8, 16, tzinfo=UTC)


def claim(
    model_key: str,
    support: CapabilitySupport,
) -> CapabilityClaim:
    return CapabilityClaim(
        model_key=model_key,
        capability=Capability.IMAGE_EDIT,
        support=support,
        confidence=ClaimConfidence.VERIFIED_DOCS,
        observed_at=NOW,
        source_ref="test-source",
    )


def price(
    model_key: str,
    *,
    expired: bool = False,
) -> PricingSnapshot:
    return PricingSnapshot(
        pricing_snapshot_id=f"price:{model_key}",
        model_key=model_key,
        metric="image",
        currency="USD",
        unit="per_image",
        price=Decimal("0.10"),
        effective_from=NOW - timedelta(days=10),
        observed_at=NOW - timedelta(days=10),
        expires_at=(
            NOW - timedelta(days=1)
            if expired
            else NOW + timedelta(days=10)
        ),
        source_ref="test-source",
    )


def model(
    model_key: str,
    provider: str,
    support: CapabilitySupport,
    *,
    expired_price: bool = False,
) -> ModelRecord:
    return ModelRecord(
        model_key=model_key,
        provider=provider,
        model=model_key.split(":", 1)[1],
        lifecycle=ModelLifecycle.STABLE,
        route_eligible=True,
        observed_at=NOW,
        source_refs=("test-source",),
        claims=(claim(model_key, support),),
        prices=(price(model_key, expired=expired_price),),
        revision_id=f"rev:{model_key}",
    )


def snapshot(
    version: str,
    records: tuple[ModelRecord, ...],
) -> RegistrySnapshot:
    payload = {
        "version": version,
        "models": [record.model_key for record in records],
    }
    checksum = registry_checksum(payload)
    return RegistrySnapshot(
        snapshot_id=f"registry:{version}:{checksum[:8]}",
        version=version,
        checksum_sha256=checksum,
        observed_at=NOW,
        published_at=NOW,
        models={
            record.model_key: record
            for record in records
        },
        routing_profiles={
            "image-edit-precision": RoutingProfile(
                name="image-edit-precision",
                required_capabilities=(Capability.IMAGE_EDIT,),
                candidate_model_keys=tuple(
                    record.model_key
                    for record in records
                ),
                selection_gate="test",
            )
        },
        source_ref="test",
    )


def test_node07_seed_preserves_truth_without_synthetic_scores() -> None:
    value = load_seed_snapshot(ROOT)
    providers = {
        record.provider
        for record in value.models.values()
    }
    assert len(providers) == 5
    assert len(value.models) == 28
    assert len(value.routing_profiles) == 15
    assert all(
        not record.benchmarks
        for record in value.models.values()
    )
    assert any(
        record.lifecycle is ModelLifecycle.DEPRECATED
        and not record.route_eligible
        for record in value.models.values()
    )
    assert all(
        record.source_refs
        for record in value.models.values()
    )
    assert all(
        claim_item.source_ref
        and claim_item.observed_at.tzinfo is not None
        for record in value.models.values()
        for claim_item in record.claims
    )


def test_unknown_and_partial_claims_are_not_full_support() -> None:
    full = model("alpha:full", "alpha", CapabilitySupport.FULL)
    partial = model(
        "alpha:partial",
        "alpha",
        CapabilitySupport.PARTIAL,
    )
    unknown = model(
        "alpha:unknown",
        "alpha",
        CapabilitySupport.UNKNOWN,
    )
    value = snapshot("1", (full, partial, unknown))

    default = value.list_models(Capability.IMAGE_EDIT)
    assert [item.model_key for item in default] == [
        "alpha:full"
    ]

    with_partial = value.list_models(
        Capability.IMAGE_EDIT,
        allow_partial=True,
    )
    assert [item.model_key for item in with_partial] == [
        "alpha:full",
        "alpha:partial",
    ]
    assert "alpha:unknown" not in {
        item.model_key
        for item in with_partial
    }


def test_expired_price_is_live_filtered_but_kept_for_history() -> None:
    record = model(
        "alpha:priced",
        "alpha",
        CapabilitySupport.FULL,
        expired_price=True,
    )
    value = snapshot("1", (record,))
    assert value.get_pricing("alpha:priced", NOW) == ()
    historical = value.get_pricing(
        "alpha:priced",
        NOW,
        allow_stale_history=True,
    )
    assert len(historical) == 1
    assert historical[0].price == Decimal("0.10")


def test_org_policy_filters_provider_and_version_must_increase() -> None:
    alpha = model(
        "alpha:a",
        "alpha",
        CapabilitySupport.FULL,
    )
    beta = model(
        "beta:b",
        "beta",
        CapabilitySupport.FULL,
    )
    registry = CapabilityRegistry(
        snapshot("1", (alpha, beta))
    )
    registry.set_policy(
        OrganizationModelPolicy(
            organization_id=ORG,
            disabled_providers=frozenset({"beta"}),
        )
    )
    found = registry.list_models(
        Capability.IMAGE_EDIT,
        organization_id=ORG,
    )
    assert [item.provider for item in found] == ["alpha"]
    try:
        registry.set_policy(
            OrganizationModelPolicy(
                organization_id=ORG,
                disabled_providers=frozenset(),
                version=1,
            )
        )
    except ValueError as exc:
        assert "version must increase" in str(exc)
    else:
        raise AssertionError(
            "stale organization policy version was accepted"
        )


def test_cache_invalidation_keeps_captured_provenance() -> None:
    first = snapshot(
        "1",
        (
            model(
                "alpha:a",
                "alpha",
                CapabilitySupport.FULL,
            ),
        ),
    )
    second = snapshot(
        "2",
        (
            model(
                "beta:b",
                "beta",
                CapabilitySupport.FULL,
            ),
        ),
    )
    registry = CapabilityRegistry(first)
    pinned = registry.capture_snapshot()
    generation = registry.generation
    registry.publish(second)
    assert registry.generation == generation + 1
    assert (
        registry.capture_snapshot().snapshot_id
        == second.snapshot_id
    )
    assert pinned.snapshot_id == first.snapshot_id
    assert tuple(pinned.models) == ("alpha:a",)


def test_benchmark_versions_keep_run_and_confidence_evidence() -> None:
    older = BenchmarkScore(
        benchmark_score_id="bench:1",
        model_key="alpha:a",
        profile="image_edit_precision",
        dataset_version="dataset-v1",
        run_id="run-1",
        sample_count=100,
        score=Decimal("80"),
        confidence_low=Decimal("78"),
        confidence_high=Decimal("82"),
        observed_at=NOW - timedelta(days=1),
        source_ref="eval-run-1",
    )
    newer = BenchmarkScore(
        benchmark_score_id="bench:2",
        model_key="alpha:a",
        profile="image_edit_precision",
        dataset_version="dataset-v2",
        run_id="run-2",
        sample_count=120,
        score=Decimal("84"),
        confidence_low=Decimal("82"),
        confidence_high=Decimal("86"),
        observed_at=NOW,
        source_ref="eval-run-2",
    )
    base = model(
        "alpha:a",
        "alpha",
        CapabilitySupport.FULL,
    )
    with_scores = ModelRecord(
        model_key=base.model_key,
        provider=base.provider,
        model=base.model,
        lifecycle=base.lifecycle,
        route_eligible=base.route_eligible,
        observed_at=base.observed_at,
        source_refs=base.source_refs,
        claims=base.claims,
        prices=base.prices,
        benchmarks=(older, newer),
        revision_id=base.revision_id,
    )
    latest = with_scores.benchmark("image_edit_precision")
    assert latest is not None
    assert latest.dataset_version == "dataset-v2"
    assert latest.run_id == "run-2"
    assert latest.sample_count == 120
