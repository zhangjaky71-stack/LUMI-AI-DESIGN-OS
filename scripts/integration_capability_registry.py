from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

from lumi_model_gateway import Capability, compile_registry_seed

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "config/model-registry/registry.seed.v1.yaml"


def _dsn(name: str) -> str:
    value = os.environ[name]
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


async def main_async() -> None:
    compiled = compile_registry_seed(SEED, repository_root=ROOT)
    runtime = await asyncpg.connect(_dsn("DATABASE_URL"))
    migration = await asyncpg.connect(_dsn("MIGRATION_DATABASE_URL"))
    try:
        version = await runtime.fetchrow(
            """
            SELECT id, version, content_hash, source_registry_version
            FROM model_registry_versions
            WHERE activated_at IS NOT NULL
            ORDER BY activated_at DESC, version DESC
            LIMIT 1
            """
        )
        assert version is not None
        assert version["id"] == compiled.snapshot_id
        assert int(version["version"]) == compiled.registry_version
        assert version["content_hash"] == compiled.content_hash
        assert version["source_registry_version"] == "1.0.0"

        counts = {
            "models": await runtime.fetchval(
                "SELECT count(*) FROM model_registry_models WHERE registry_version_id = $1",
                compiled.snapshot_id,
            ),
            "claims": await runtime.fetchval(
                "SELECT count(*) FROM model_capability_claims WHERE registry_version_id = $1",
                compiled.snapshot_id,
            ),
            "pricing": await runtime.fetchval(
                "SELECT count(*) FROM model_pricing_snapshots WHERE registry_version_id = $1",
                compiled.snapshot_id,
            ),
            "benchmarks": await runtime.fetchval(
                "SELECT count(*) FROM model_benchmark_scores WHERE registry_version_id = $1",
                compiled.snapshot_id,
            ),
            "routes": await runtime.fetchval(
                "SELECT count(*) FROM model_routing_profiles WHERE registry_version_id = $1",
                compiled.snapshot_id,
            ),
        }
        assert int(counts["models"]) == 28, counts
        assert int(counts["claims"]) == len(compiled.capability_claims), counts
        assert int(counts["pricing"]) == len(compiled.pricing), counts
        assert int(counts["benchmarks"]) == 0, counts
        assert int(counts["routes"]) == 15, counts

        unknown = await runtime.fetchval(
            """
            SELECT count(*) FROM model_capability_claims
            WHERE registry_version_id = $1 AND model_key = $2 AND capability = $3
            """,
            compiled.snapshot_id,
            "openai:gpt-image-2",
            Capability.OCR_DOCUMENT.value,
        )
        assert int(unknown) == 0

        current_price = await runtime.fetchval(
            """
            SELECT count(*) FROM model_pricing_snapshots
            WHERE model_key = 'openai:gpt-5.6-sol'
              AND effective_from <= $1
              AND (valid_until IS NULL OR $1 < valid_until)
            """,
            datetime(2026, 8, 14, tzinfo=UTC),
        )
        expired_price = await runtime.fetchval(
            """
            SELECT count(*) FROM model_pricing_snapshots
            WHERE model_key = 'openai:gpt-5.6-sol'
              AND effective_from <= $1
              AND (valid_until IS NULL OR $1 < valid_until)
            """,
            datetime(2026, 9, 13, tzinfo=UTC),
        )
        assert int(current_price) > 0
        assert int(expired_price) == 0

        organization_id = await migration.fetchval(
            "SELECT id FROM organizations ORDER BY created_at LIMIT 1"
        )
        assert organization_id is not None
        await migration.execute(
            """
            INSERT INTO organization_model_policies (
                id, organization_id, policy_version, disabled_providers_json,
                denied_models_json, allowed_regions_json, preferred_models_json,
                data_handling_restrictions_json, effective_from, created_at
            ) VALUES (
                gen_random_uuid(), $1, 1, '["openai"]'::jsonb, '[]'::jsonb,
                '[]'::jsonb, '[]'::jsonb, '["no_training"]'::jsonb, now(), now()
            )
            ON CONFLICT (organization_id, policy_version) DO NOTHING
            """,
            organization_id,
        )
        disabled = await runtime.fetchval(
            """
            SELECT disabled_providers_json FROM organization_model_policies
            WHERE organization_id = $1 ORDER BY policy_version DESC LIMIT 1
            """,
            organization_id,
        )
        assert "openai" in disabled

        try:
            await runtime.execute(
                "UPDATE model_registry_versions SET source_ref = 'tampered' WHERE id = $1",
                compiled.snapshot_id,
            )
        except asyncpg.InsufficientPrivilegeError:
            pass
        else:
            raise AssertionError("lumi_app must not mutate model registry facts")
    finally:
        await runtime.close()
        await migration.close()


def main() -> int:
    asyncio.run(main_async())
    print("NODE-23 PostgreSQL capability registry integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
