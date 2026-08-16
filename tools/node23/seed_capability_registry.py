from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from lumi_model_gateway.models import Capability
from lumi_model_gateway.registry import RegistrySnapshot
from lumi_model_gateway.registry_seed import load_seed_snapshot

ROOT = Path(__file__).resolve().parents[2]


def stable_uuid(kind: str, value: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"lumi:model-registry:{kind}:{value}",
    )


async def publish_snapshot(
    connection: Any,
    snapshot: RegistrySnapshot,
) -> dict[str, int]:
    existing = await connection.fetchrow(
        "SELECT id, checksum_sha256 FROM model_registry_versions "
        "WHERE version = $1",
        snapshot.version,
    )
    if existing is not None:
        if existing["checksum_sha256"] != snapshot.checksum_sha256:
            raise RuntimeError(
                "REGISTRY_VERSION_CHECKSUM_CONFLICT: "
                "published version is immutable"
            )
        return await snapshot_counts(connection, existing["id"])

    version_id = stable_uuid("version", snapshot.version)
    async with connection.transaction():
        await connection.execute(
            """
            INSERT INTO model_registry_versions
              (id, version, checksum_sha256, status, observed_at,
               published_at, source_ref)
            VALUES ($1, $2, $3, 'published', $4, $5, $6)
            """,
            version_id,
            snapshot.version,
            snapshot.checksum_sha256,
            snapshot.observed_at,
            snapshot.published_at,
            snapshot.source_ref,
        )
        for capability in Capability:
            await connection.execute(
                """
                INSERT INTO model_capabilities
                  (capability_key, description)
                VALUES ($1, $2)
                ON CONFLICT (capability_key) DO NOTHING
                """,
                capability.value,
                f"LUMI model capability {capability.value}",
            )

        provider_ids: dict[str, UUID] = {}
        definition_ids: dict[str, UUID] = {}
        for record in snapshot.models.values():
            provider_id = provider_ids.setdefault(
                record.provider,
                stable_uuid("provider", record.provider),
            )
            await connection.execute(
                """
                INSERT INTO model_providers
                  (id, provider_key, display_name, source_ref, observed_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (provider_key) DO NOTHING
                """,
                provider_id,
                record.provider,
                record.provider,
                record.source_refs[0],
                record.observed_at,
            )
            definition_id = stable_uuid(
                "model",
                record.model_key,
            )
            definition_ids[record.model_key] = definition_id
            await connection.execute(
                """
                INSERT INTO model_definitions
                  (id, provider_id, model_key, provider_model_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (model_key) DO NOTHING
                """,
                definition_id,
                provider_id,
                record.model_key,
                record.model,
            )
            revision_id = stable_uuid(
                "revision",
                (
                    f"{snapshot.version}:"
                    f"{record.model_key}:"
                    f"{record.revision_id}"
                ),
            )
            await connection.execute(
                """
                INSERT INTO model_revisions
                  (id, registry_version_id, model_definition_id,
                   revision_key, lifecycle, route_eligible, regions,
                   observed_at, source_refs, metadata)
                VALUES
                  ($1, $2, $3, $4, $5, $6, $7::jsonb,
                   $8, $9::jsonb, $10::jsonb)
                """,
                revision_id,
                version_id,
                definition_id,
                record.revision_id,
                record.lifecycle.value,
                record.route_eligible,
                json.dumps(sorted(record.regions)),
                record.observed_at,
                json.dumps(record.source_refs),
                json.dumps(dict(record.metadata), default=str),
            )
            for claim in record.claims:
                claim_id = stable_uuid(
                    "claim",
                    (
                        f"{snapshot.version}:"
                        f"{record.model_key}:"
                        f"{claim.capability.value}"
                    ),
                )
                await connection.execute(
                    """
                    INSERT INTO model_capability_claims
                      (id, registry_version_id, model_revision_id,
                       capability_key, support, limits, confidence,
                       observed_at, source_ref)
                    VALUES
                      ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
                    """,
                    claim_id,
                    version_id,
                    revision_id,
                    claim.capability.value,
                    claim.support.value,
                    json.dumps(dict(claim.limits), default=str),
                    claim.confidence.value,
                    claim.observed_at,
                    claim.source_ref,
                )
            for price in record.prices:
                price_id = stable_uuid(
                    "price",
                    price.pricing_snapshot_id,
                )
                await connection.execute(
                    """
                    INSERT INTO model_pricing_snapshots
                      (id, registry_version_id, model_revision_id,
                       metric, currency, unit, price, minimum_charge,
                       region, effective_from, observed_at, expires_at,
                       source_ref)
                    VALUES
                      ($1, $2, $3, $4, $5, $6, $7, $8,
                       $9, $10, $11, $12, $13)
                    """,
                    price_id,
                    version_id,
                    revision_id,
                    price.metric,
                    price.currency,
                    price.unit,
                    price.price,
                    price.minimum_charge,
                    price.region or "global",
                    price.effective_from,
                    price.observed_at,
                    price.expires_at,
                    price.source_ref,
                )
            for benchmark in record.benchmarks:
                benchmark_id = stable_uuid(
                    "benchmark",
                    benchmark.benchmark_score_id,
                )
                await connection.execute(
                    """
                    INSERT INTO model_benchmark_scores
                      (id, registry_version_id, model_revision_id,
                       profile, dataset_version, run_id, sample_count,
                       score, confidence_low, confidence_high, statistics,
                       observed_at, source_ref)
                    VALUES
                      ($1, $2, $3, $4, $5, $6, $7, $8,
                       $9, $10, $11::jsonb, $12, $13)
                    """,
                    benchmark_id,
                    version_id,
                    revision_id,
                    benchmark.profile,
                    benchmark.dataset_version,
                    benchmark.run_id,
                    benchmark.sample_count,
                    benchmark.score,
                    benchmark.confidence_low,
                    benchmark.confidence_high,
                    json.dumps(
                        dict(benchmark.statistics),
                        default=str,
                    ),
                    benchmark.observed_at,
                    benchmark.source_ref,
                )

        for profile in snapshot.routing_profiles.values():
            profile_id = stable_uuid(
                "profile",
                f"{snapshot.version}:{profile.name}",
            )
            weights = {
                "quality": str(profile.weights.quality),
                "constraint": str(profile.weights.constraint),
                "cost": str(profile.weights.cost),
                "latency": str(profile.weights.latency),
                "availability": str(
                    profile.weights.availability
                ),
            }
            await connection.execute(
                """
                INSERT INTO model_routing_profiles
                  (id, registry_version_id, profile_key,
                   required_capabilities, weights, minimum_quality,
                   selection_gate, source_ref)
                VALUES
                  ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
                """,
                profile_id,
                version_id,
                profile.name,
                json.dumps(
                    [
                        item.value
                        for item in profile.required_capabilities
                    ]
                ),
                json.dumps(weights),
                profile.minimum_quality,
                profile.selection_gate,
                profile.source_ref,
            )
            stable_fallbacks = set(
                profile.stable_fallback_model_keys
            )
            for ordinal, model_key in enumerate(
                profile.candidate_model_keys
            ):
                await connection.execute(
                    """
                    INSERT INTO model_routing_profile_candidates
                      (routing_profile_id, model_definition_id,
                       ordinal, stable_fallback)
                    VALUES ($1, $2, $3, $4)
                    """,
                    profile_id,
                    definition_ids[model_key],
                    ordinal,
                    model_key in stable_fallbacks,
                )

    return await snapshot_counts(connection, version_id)


async def snapshot_counts(
    connection: Any,
    version_id: UUID,
) -> dict[str, int]:
    queries = {
        "providers": "SELECT count(*) FROM model_providers",
        "models": (
            "SELECT count(*) FROM model_revisions "
            "WHERE registry_version_id = $1"
        ),
        "claims": (
            "SELECT count(*) FROM model_capability_claims "
            "WHERE registry_version_id = $1"
        ),
        "prices": (
            "SELECT count(*) FROM model_pricing_snapshots "
            "WHERE registry_version_id = $1"
        ),
        "benchmarks": (
            "SELECT count(*) FROM model_benchmark_scores "
            "WHERE registry_version_id = $1"
        ),
        "profiles": (
            "SELECT count(*) FROM model_routing_profiles "
            "WHERE registry_version_id = $1"
        ),
    }
    result: dict[str, int] = {}
    for key, query in queries.items():
        args = (version_id,) if "$1" in query else ()
        value = await connection.fetchval(query, *args)
        result[key] = int(value or 0)
    return result


async def run(dsn: str) -> None:
    try:
        import asyncpg
    except ImportError as exc:
        raise RuntimeError(
            "asyncpg is required for NODE-23 PostgreSQL seed publishing"
        ) from exc
    snapshot = load_seed_snapshot(ROOT)
    connection = await asyncpg.connect(dsn)
    try:
        counts = await publish_snapshot(connection, snapshot)
    finally:
        await connection.close()
    print(
        json.dumps(
            {"snapshot_id": snapshot.snapshot_id, **counts},
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.dsn))


if __name__ == "__main__":
    main()
