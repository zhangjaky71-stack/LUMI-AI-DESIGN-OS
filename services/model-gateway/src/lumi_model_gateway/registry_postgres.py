from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from .models import Capability
from .registry import (
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
    RoutingWeights,
)


class PostgresCapabilityRegistryStore:
    """Read-side adapter for immutable NODE-23 PostgreSQL snapshots.

    The driver is intentionally duck-typed. Production composition may pass an asyncpg
    connection without making asyncpg importable from every Model Gateway caller.
    """

    async def load_snapshot(
        self,
        connection: Any,
        *,
        version: str | None = None,
    ) -> RegistrySnapshot:
        if version is None:
            version_row = await connection.fetchrow(
                """
                SELECT id, version, checksum_sha256, observed_at, published_at, source_ref
                FROM model_registry_versions
                WHERE status = 'published'
                ORDER BY published_at DESC, version DESC
                LIMIT 1
                """
            )
        else:
            version_row = await connection.fetchrow(
                """
                SELECT id, version, checksum_sha256, observed_at, published_at, source_ref
                FROM model_registry_versions
                WHERE version = $1 AND status = 'published'
                """,
                version,
            )
        if version_row is None:
            raise LookupError("no published model registry snapshot")
        version_id = version_row["id"]
        version_value = str(version_row["version"])

        model_rows = await connection.fetch(
            """
            SELECT
              r.id AS revision_id,
              r.revision_key,
              r.lifecycle,
              r.route_eligible,
              r.regions,
              r.observed_at,
              r.source_refs,
              r.metadata,
              d.id AS definition_id,
              d.model_key,
              d.provider_model_id,
              p.provider_key
            FROM model_revisions r
            JOIN model_definitions d ON d.id = r.model_definition_id
            JOIN model_providers p ON p.id = d.provider_id
            WHERE r.registry_version_id = $1
            ORDER BY d.model_key
            """,
            version_id,
        )
        claim_rows = await connection.fetch(
            """
            SELECT id, model_revision_id, capability_key, support, limits,
                   confidence, observed_at, source_ref
            FROM model_capability_claims
            WHERE registry_version_id = $1
            ORDER BY model_revision_id, capability_key
            """,
            version_id,
        )
        price_rows = await connection.fetch(
            """
            SELECT id, model_revision_id, metric, currency, unit, price,
                   minimum_charge, region, effective_from, observed_at,
                   expires_at, source_ref
            FROM model_pricing_snapshots
            WHERE registry_version_id = $1
            ORDER BY model_revision_id, metric, effective_from
            """,
            version_id,
        )
        benchmark_rows = await connection.fetch(
            """
            SELECT id, model_revision_id, profile, dataset_version, run_id,
                   sample_count, score, confidence_low, confidence_high,
                   statistics, observed_at, source_ref
            FROM model_benchmark_scores
            WHERE registry_version_id = $1
            ORDER BY model_revision_id, profile, observed_at
            """,
            version_id,
        )
        profile_rows = await connection.fetch(
            """
            SELECT id, profile_key, required_capabilities, weights,
                   minimum_quality, selection_gate, source_ref
            FROM model_routing_profiles
            WHERE registry_version_id = $1
            ORDER BY profile_key
            """,
            version_id,
        )
        candidate_rows = await connection.fetch(
            """
            SELECT c.routing_profile_id, d.model_key, c.ordinal, c.stable_fallback
            FROM model_routing_profile_candidates c
            JOIN model_definitions d ON d.id = c.model_definition_id
            JOIN model_routing_profiles p ON p.id = c.routing_profile_id
            WHERE p.registry_version_id = $1
            ORDER BY c.routing_profile_id, c.ordinal
            """,
            version_id,
        )

        claims_by_revision: dict[UUID, list[CapabilityClaim]] = defaultdict(
            list
        )
        for row in claim_rows:
            claims_by_revision[row["model_revision_id"]].append(
                CapabilityClaim(
                    model_key="__resolved_below__",
                    capability=Capability(str(row["capability_key"])),
                    support=CapabilitySupport(str(row["support"])),
                    limits=dict(row["limits"] or {}),
                    confidence=ClaimConfidence(str(row["confidence"])),
                    observed_at=_aware(row["observed_at"]),
                    source_ref=str(row["source_ref"]),
                )
            )

        prices_by_revision: dict[UUID, list[PricingSnapshot]] = defaultdict(
            list
        )
        for row in price_rows:
            region_value = row["region"]
            expires_at = row["expires_at"]
            prices_by_revision[row["model_revision_id"]].append(
                PricingSnapshot(
                    pricing_snapshot_id=str(row["id"]),
                    model_key="__resolved_below__",
                    metric=str(row["metric"]),
                    currency=str(row["currency"]),
                    unit=str(row["unit"]),
                    price=Decimal(str(row["price"])),
                    minimum_charge=(
                        None
                        if row["minimum_charge"] is None
                        else Decimal(str(row["minimum_charge"]))
                    ),
                    region=(
                        None
                        if region_value in (None, "global")
                        else str(region_value)
                    ),
                    effective_from=_aware(row["effective_from"]),
                    observed_at=_aware(row["observed_at"]),
                    expires_at=(
                        None
                        if expires_at is None
                        else _aware(expires_at)
                    ),
                    source_ref=str(row["source_ref"]),
                )
            )

        benchmarks_by_revision: dict[UUID, list[BenchmarkScore]] = defaultdict(
            list
        )
        for row in benchmark_rows:
            benchmarks_by_revision[row["model_revision_id"]].append(
                BenchmarkScore(
                    benchmark_score_id=str(row["id"]),
                    model_key="__resolved_below__",
                    profile=str(row["profile"]),
                    dataset_version=str(row["dataset_version"]),
                    run_id=str(row["run_id"]),
                    sample_count=int(row["sample_count"]),
                    score=Decimal(str(row["score"])),
                    confidence_low=(
                        None
                        if row["confidence_low"] is None
                        else Decimal(str(row["confidence_low"]))
                    ),
                    confidence_high=(
                        None
                        if row["confidence_high"] is None
                        else Decimal(str(row["confidence_high"]))
                    ),
                    statistics=dict(row["statistics"] or {}),
                    observed_at=_aware(row["observed_at"]),
                    source_ref=str(row["source_ref"]),
                )
            )

        models: dict[str, ModelRecord] = {}
        for row in model_rows:
            revision_id = row["revision_id"]
            model_key = str(row["model_key"])
            claims = tuple(
                _replace_claim_model_key(item, model_key)
                for item in claims_by_revision[revision_id]
            )
            prices = tuple(
                _replace_price_model_key(item, model_key)
                for item in prices_by_revision[revision_id]
            )
            benchmarks = tuple(
                _replace_benchmark_model_key(item, model_key)
                for item in benchmarks_by_revision[revision_id]
            )
            models[model_key] = ModelRecord(
                model_key=model_key,
                provider=str(row["provider_key"]),
                model=str(row["provider_model_id"]),
                lifecycle=ModelLifecycle(str(row["lifecycle"])),
                route_eligible=bool(row["route_eligible"]),
                observed_at=_aware(row["observed_at"]),
                source_refs=tuple(
                    str(item) for item in row["source_refs"]
                ),
                claims=claims,
                prices=prices,
                benchmarks=benchmarks,
                regions=frozenset(
                    str(item) for item in row["regions"]
                ),
                revision_id=str(row["revision_key"]),
                metadata=dict(row["metadata"] or {}),
            )

        candidates_by_profile: dict[
            UUID,
            list[tuple[str, bool]],
        ] = defaultdict(list)
        for row in candidate_rows:
            candidates_by_profile[row["routing_profile_id"]].append(
                (
                    str(row["model_key"]),
                    bool(row["stable_fallback"]),
                )
            )
        profiles: dict[str, RoutingProfile] = {}
        for row in profile_rows:
            candidates = candidates_by_profile[row["id"]]
            weight_payload = dict(row["weights"] or {})
            profile = RoutingProfile(
                name=str(row["profile_key"]),
                required_capabilities=tuple(
                    Capability(str(item))
                    for item in row["required_capabilities"]
                ),
                candidate_model_keys=tuple(
                    item[0] for item in candidates
                ),
                stable_fallback_model_keys=tuple(
                    item[0] for item in candidates if item[1]
                ),
                selection_gate=str(row["selection_gate"]),
                minimum_quality=(
                    None
                    if row["minimum_quality"] is None
                    else Decimal(str(row["minimum_quality"]))
                ),
                weights=RoutingWeights(
                    quality=Decimal(str(weight_payload["quality"])),
                    constraint=Decimal(
                        str(weight_payload["constraint"])
                    ),
                    cost=Decimal(str(weight_payload["cost"])),
                    latency=Decimal(str(weight_payload["latency"])),
                    availability=Decimal(
                        str(weight_payload["availability"])
                    ),
                ),
                source_ref=str(row["source_ref"]),
            )
            profiles[profile.name] = profile

        checksum = str(version_row["checksum_sha256"])
        return RegistrySnapshot(
            snapshot_id=f"registry:{version_value}:{checksum[:16]}",
            version=version_value,
            checksum_sha256=checksum,
            observed_at=_aware(version_row["observed_at"]),
            published_at=_aware(version_row["published_at"]),
            models=models,
            routing_profiles=profiles,
            source_ref=str(version_row["source_ref"]),
        )

    async def load_organization_policy(
        self,
        connection: Any,
        organization_id: UUID,
    ) -> OrganizationModelPolicy | None:
        async with connection.transaction():
            await connection.execute(
                "SELECT set_config('app.current_organization_id', $1, true)",
                str(organization_id),
            )
            row = await connection.fetchrow(
                """
                SELECT organization_id, version, disabled_providers, allowed_regions,
                       preferred_models, max_cost_class, data_handling_restrictions
                FROM organization_model_policies
                WHERE organization_id = $1
                """,
                organization_id,
            )
        if row is None:
            return None
        return OrganizationModelPolicy(
            organization_id=row["organization_id"],
            version=int(row["version"]),
            disabled_providers=frozenset(
                str(item) for item in row["disabled_providers"]
            ),
            allowed_regions=frozenset(
                str(item) for item in row["allowed_regions"]
            ),
            preferred_models=tuple(
                str(item) for item in row["preferred_models"]
            ),
            max_cost_class=row["max_cost_class"],
            data_handling_restrictions=frozenset(
                str(item)
                for item in row["data_handling_restrictions"]
            ),
        )

    async def refresh(
        self,
        registry: CapabilityRegistry,
        connection: Any,
    ) -> bool:
        current = registry.capture_snapshot()
        latest = await self.load_snapshot(connection)
        if latest.snapshot_id == current.snapshot_id:
            if latest.checksum_sha256 != current.checksum_sha256:
                raise RuntimeError(
                    "REGISTRY_SNAPSHOT_ID_CHECKSUM_CONFLICT"
                )
            return False
        registry.publish(latest)
        return True


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _replace_claim_model_key(
    value: CapabilityClaim,
    model_key: str,
) -> CapabilityClaim:
    return CapabilityClaim(
        model_key=model_key,
        capability=value.capability,
        support=value.support,
        limits=value.limits,
        confidence=value.confidence,
        observed_at=value.observed_at,
        source_ref=value.source_ref,
    )


def _replace_price_model_key(
    value: PricingSnapshot,
    model_key: str,
) -> PricingSnapshot:
    return PricingSnapshot(
        pricing_snapshot_id=value.pricing_snapshot_id,
        model_key=model_key,
        metric=value.metric,
        currency=value.currency,
        unit=value.unit,
        price=value.price,
        minimum_charge=value.minimum_charge,
        region=value.region,
        effective_from=value.effective_from,
        observed_at=value.observed_at,
        expires_at=value.expires_at,
        source_ref=value.source_ref,
    )


def _replace_benchmark_model_key(
    value: BenchmarkScore,
    model_key: str,
) -> BenchmarkScore:
    return BenchmarkScore(
        benchmark_score_id=value.benchmark_score_id,
        model_key=model_key,
        profile=value.profile,
        dataset_version=value.dataset_version,
        run_id=value.run_id,
        sample_count=value.sample_count,
        score=value.score,
        confidence_low=value.confidence_low,
        confidence_high=value.confidence_high,
        statistics=value.statistics,
        observed_at=value.observed_at,
        source_ref=value.source_ref,
    )
