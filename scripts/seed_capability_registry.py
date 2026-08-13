from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import asyncpg

from lumi_model_gateway.capability_registry import RegistrySnapshot, compile_registry_seed

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "config/model-registry/registry.seed.v1.yaml"


def _dsn(name: str) -> str:
    value = os.environ[name]
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


def _id(snapshot: RegistrySnapshot, kind: str, identity: str):
    return uuid5(NAMESPACE_URL, f"lumi:{snapshot.content_hash}:{kind}:{identity}")


async def seed(snapshot: RegistrySnapshot, *, dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            existing = await connection.fetchrow(
                "SELECT id, content_hash FROM model_registry_versions WHERE version = $1",
                snapshot.registry_version,
            )
            if existing is not None and existing["content_hash"] != snapshot.content_hash:
                raise RuntimeError("MODEL_REGISTRY_VERSION_CONTENT_CONFLICT")
            await connection.execute(
                """
                INSERT INTO model_registry_versions (
                    id, version, source_registry_version, content_hash, observed_at,
                    source_ref, activated_at, created_at
                ) VALUES ($1,$2,$3,$4,$5,$6,now(),now())
                ON CONFLICT (version) DO UPDATE SET
                    activated_at = now()
                WHERE model_registry_versions.content_hash = EXCLUDED.content_hash
                """,
                snapshot.snapshot_id,
                snapshot.registry_version,
                snapshot.source_registry_version,
                snapshot.content_hash,
                snapshot.observed_at,
                snapshot.source_ref,
            )
            for model in snapshot.models:
                await connection.execute(
                    """
                    INSERT INTO model_registry_models (
                        id, registry_version_id, model_key, provider, model, lifecycle,
                        route_eligible, regions_json, latency_class, benchmark_status,
                        observed_at, source_ref, created_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,$11,$12,now())
                    ON CONFLICT (registry_version_id, model_key) DO NOTHING
                    """,
                    _id(snapshot, "model", model.model_key),
                    snapshot.snapshot_id,
                    model.model_key,
                    model.provider,
                    model.model,
                    model.lifecycle,
                    model.route_eligible,
                    json.dumps(list(model.regions)),
                    model.latency_class,
                    model.benchmark_status,
                    model.observed_at,
                    model.source_ref,
                )
            for claim in snapshot.capability_claims:
                identity = f"{claim.model_key}:{claim.capability.value}"
                await connection.execute(
                    """
                    INSERT INTO model_capability_claims (
                        id, registry_version_id, model_key, capability, support,
                        limits_json, confidence, observed_at, source_ref, created_at
                    ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,now())
                    ON CONFLICT (registry_version_id, model_key, capability) DO NOTHING
                    """,
                    _id(snapshot, "claim", identity),
                    snapshot.snapshot_id,
                    claim.model_key,
                    claim.capability.value,
                    claim.support.value,
                    claim.limits_json,
                    claim.confidence.value,
                    claim.observed_at,
                    claim.source_ref,
                )
            for price in snapshot.pricing:
                await connection.execute(
                    """
                    INSERT INTO model_pricing_snapshots (
                        id, registry_version_id, price_snapshot_key, model_key, currency,
                        unit, price, minimum_charge, effective_from, valid_until,
                        observed_at, source_ref, created_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,now())
                    ON CONFLICT (price_snapshot_key) DO NOTHING
                    """,
                    _id(snapshot, "price", price.price_snapshot_id),
                    snapshot.snapshot_id,
                    price.price_snapshot_id,
                    price.model_key,
                    price.currency,
                    price.unit,
                    price.price,
                    price.minimum_charge,
                    price.effective_from,
                    price.valid_until,
                    price.observed_at,
                    price.source_ref,
                )
            for profile in snapshot.routing_profiles:
                await connection.execute(
                    """
                    INSERT INTO model_routing_profiles (
                        id, registry_version_id, profile, required_capabilities_json,
                        candidate_models_json, weights_json, minimum_json, observed_at,
                        source_ref, created_at
                    ) VALUES ($1,$2,$3,$4::jsonb,$5::jsonb,$6::jsonb,$7::jsonb,$8,$9,now())
                    ON CONFLICT (registry_version_id, profile) DO NOTHING
                    """,
                    _id(snapshot, "route", profile.profile),
                    snapshot.snapshot_id,
                    profile.profile,
                    json.dumps([item.value for item in profile.required_capabilities]),
                    json.dumps(list(profile.candidate_models)),
                    profile.weights_json,
                    profile.minimum_json,
                    profile.observed_at,
                    profile.source_ref,
                )
            for benchmark in snapshot.benchmarks:
                identity = (
                    f"{benchmark.model_key}:{benchmark.profile}:"
                    f"{benchmark.dataset_version}:{benchmark.run_id}"
                )
                await connection.execute(
                    """
                    INSERT INTO model_benchmark_scores (
                        id, registry_version_id, model_key, profile, score,
                        dataset_version, run_id, sample_count, statistics_json,
                        confidence, observed_at, source_ref, created_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,now())
                    ON CONFLICT (
                        registry_version_id, model_key, profile, dataset_version, run_id
                    ) DO NOTHING
                    """,
                    _id(snapshot, "benchmark", identity),
                    snapshot.snapshot_id,
                    benchmark.model_key,
                    benchmark.profile,
                    benchmark.score,
                    benchmark.dataset_version,
                    benchmark.run_id,
                    benchmark.sample_count,
                    benchmark.statistics_json,
                    benchmark.confidence.value,
                    benchmark.observed_at,
                    benchmark.source_ref,
                )
    finally:
        await connection.close()


async def main_async() -> None:
    snapshot = compile_registry_seed(SEED, repository_root=ROOT)
    await seed(snapshot, dsn=_dsn("MIGRATION_DATABASE_URL"))
    print(
        "NODE-23 registry seed: "
        f"version={snapshot.registry_version} models={len(snapshot.models)} "
        f"claims={len(snapshot.capability_claims)} pricing={len(snapshot.pricing)} "
        f"hash={snapshot.content_hash}"
    )


def main() -> int:
    asyncio.run(main_async())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
