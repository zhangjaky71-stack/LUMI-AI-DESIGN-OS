from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from lumi_model_gateway.models import Capability
from lumi_model_gateway.registry import (
    CapabilityClaim,
    CapabilityRegistry,
    CapabilitySupport,
    ClaimConfidence,
    ModelLifecycle,
    ModelRecord,
    RegistrySnapshot,
    RoutingProfile,
    registry_checksum,
)
from lumi_model_gateway.routing_profile_evaluator import (
    RoutingEvidence,
    RoutingProfileEvaluator,
)

ORG = UUID("01910000-0000-7000-8000-000000000521")
NOW = datetime(2026, 8, 16, tzinfo=UTC)


def build_registry() -> CapabilityRegistry:
    models = {}
    for key in ("alpha:a", "beta:b"):
        provider, model = key.split(":", 1)
        models[key] = ModelRecord(
            model_key=key,
            provider=provider,
            model=model,
            lifecycle=ModelLifecycle.STABLE,
            route_eligible=True,
            observed_at=NOW,
            source_refs=("test",),
            claims=(
                CapabilityClaim(
                    model_key=key,
                    capability=Capability.IMAGE_EDIT,
                    support=CapabilitySupport.FULL,
                    confidence=ClaimConfidence.LIVE_TEST,
                    observed_at=NOW,
                    source_ref="test",
                ),
            ),
            revision_id=f"revision:{key}",
        )
    checksum = registry_checksum(
        {"models": sorted(models)}
    )
    snapshot = RegistrySnapshot(
        snapshot_id=f"registry:test:{checksum[:8]}",
        version="test",
        checksum_sha256=checksum,
        observed_at=NOW,
        published_at=NOW,
        models=models,
        routing_profiles={
            "image-edit-precision": RoutingProfile(
                name="image-edit-precision",
                required_capabilities=(Capability.IMAGE_EDIT,),
                candidate_model_keys=(
                    "alpha:a",
                    "beta:b",
                ),
                selection_gate="image-edit-v1",
            )
        },
        source_ref="test",
    )
    return CapabilityRegistry(snapshot)


def test_incomplete_evidence_does_not_create_a_winner() -> None:
    evaluator = RoutingProfileEvaluator(build_registry())
    result = evaluator.evaluate(
        "image-edit-precision",
        organization_id=ORG,
        evidence={},
    )
    assert [item.model_key for item in result] == [
        "alpha:a",
        "beta:b",
    ]
    assert all(
        item.score is None and not item.complete
        for item in result
    )
    assert all(
        any(
            code.startswith("insufficient_evidence:")
            for code in item.reason_codes
        )
        for item in result
    )


def test_complete_evidence_uses_versioned_profile_weights() -> None:
    evaluator = RoutingProfileEvaluator(build_registry())
    result = evaluator.evaluate(
        "image-edit-precision",
        organization_id=ORG,
        evidence={
            "alpha:a": RoutingEvidence(
                quality=Decimal("100"),
                constraint=Decimal("100"),
                cost=Decimal("80"),
                latency=Decimal("80"),
                availability=Decimal("100"),
            ),
            "beta:b": RoutingEvidence(
                quality=Decimal("80"),
                constraint=Decimal("80"),
                cost=Decimal("90"),
                latency=Decimal("90"),
                availability=Decimal("100"),
            ),
        },
    )
    assert all(
        item.complete and item.score is not None
        for item in result
    )
    assert result[0].score is not None
    assert result[1].score is not None
    assert result[0].score > result[1].score
    assert result[0].model_key == "alpha:a"
