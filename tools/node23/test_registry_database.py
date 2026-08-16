from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

from lumi_model_gateway.registry_postgres import PostgresCapabilityRegistryStore
from lumi_model_gateway.registry_seed import load_seed_snapshot

from seed_capability_registry import publish_snapshot

ROOT = Path(__file__).resolve().parents[2]
GLOBAL_TABLES = (
    "model_registry_versions",
    "model_providers",
    "model_definitions",
    "model_revisions",
    "model_capabilities",
    "model_capability_claims",
    "model_pricing_snapshots",
    "model_benchmark_scores",
    "model_routing_profiles",
    "model_routing_profile_candidates",
)


async def require_tables(connection: Any) -> None:
    rows = await connection.fetch(
        """
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename = ANY($1::text[])
        """,
        [*GLOBAL_TABLES, "organization_model_policies"],
    )
    found = {str(row["tablename"]) for row in rows}
    expected = {*GLOBAL_TABLES, "organization_model_policies"}
    if found != expected:
        raise AssertionError(f"registry table mismatch missing={sorted(expected - found)}")


async def require_policy_rls(connection: Any) -> None:
    enabled = await connection.fetchval(
        "SELECT relrowsecurity FROM pg_class WHERE relname = 'organization_model_policies'"
    )
    if enabled is not True:
        raise AssertionError("organization_model_policies RLS is not enabled")
    policy_count = await connection.fetchval(
        """
        SELECT count(*) FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'organization_model_policies'
          AND policyname = 'tenant_isolation_organization_model_policies'
        """
    )
    if int(policy_count or 0) != 1:
        raise AssertionError("organization model policy tenant RLS policy missing")


async def require_runtime_global_read_only(connection: Any) -> None:
    role_exists = await connection.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app')"
    )
    if not role_exists:
        return
    for table in GLOBAL_TABLES:
        can_select = await connection.fetchval(
            "SELECT has_table_privilege('lumi_app', $1, 'SELECT')",
            table,
        )
        can_insert = await connection.fetchval(
            "SELECT has_table_privilege('lumi_app', $1, 'INSERT')",
            table,
        )
        can_update = await connection.fetchval(
            "SELECT has_table_privilege('lumi_app', $1, 'UPDATE')",
            table,
        )
        can_delete = await connection.fetchval(
            "SELECT has_table_privilege('lumi_app', $1, 'DELETE')",
            table,
        )
        if can_select is not True or any((can_insert, can_update, can_delete)):
            raise AssertionError(f"lumi_app global registry grants are not read-only: {table}")


async def require_seed_round_trip(connection: Any) -> None:
    expected = load_seed_snapshot(ROOT)
    first = await publish_snapshot(connection, expected)
    second = await publish_snapshot(connection, expected)
    if first != second:
        raise AssertionError("idempotent seed replay changed registry counts")
    if first["providers"] != 5 or first["models"] != 28 or first["profiles"] != 15:
        raise AssertionError(f"NODE-07 seed cardinality changed: {first}")
    if first["benchmarks"] != 0:
        raise AssertionError("NOT_MEASURED seed created synthetic benchmark scores")

    raw_price_count = 0
    config = __import__("json").loads(
        (ROOT / "config/model-registry.seed.json").read_text(encoding="utf-8")
    )
    for provider_file in config["provider_files"]:
        payload = __import__("json").loads(
            (ROOT / provider_file).read_text(encoding="utf-8")
        )
        raw_price_count += sum(
            len(model.get("pricing") or []) for model in payload.get("models") or []
        )
    if first["prices"] != raw_price_count:
        raise AssertionError(
            f"pricing normalization lost records raw={raw_price_count} db={first['prices']}"
        )

    store = PostgresCapabilityRegistryStore()
    restored = await store.load_snapshot(connection, version=expected.version)
    if restored.checksum_sha256 != expected.checksum_sha256:
        raise AssertionError("PostgreSQL round-trip changed snapshot checksum identity")
    if len(restored.models) != len(expected.models):
        raise AssertionError("PostgreSQL round-trip changed model cardinality")
    if len(restored.routing_profiles) != len(expected.routing_profiles):
        raise AssertionError("PostgreSQL round-trip changed routing profile cardinality")

    conflict = replace(expected, checksum_sha256="0" * 64)
    try:
        await publish_snapshot(connection, conflict)
    except RuntimeError as exc:
        if "REGISTRY_VERSION_CHECKSUM_CONFLICT" not in str(exc):
            raise
    else:
        raise AssertionError("same registry version accepted a different checksum")


async def run(dsn: str) -> None:
    try:
        import asyncpg
    except ImportError as exc:
        raise RuntimeError("asyncpg is required for NODE-23 DB verification") from exc
    connection = await asyncpg.connect(dsn)
    try:
        await require_tables(connection)
        await require_policy_rls(connection)
        await require_runtime_global_read_only(connection)
        await require_seed_round_trip(connection)
    finally:
        await connection.close()
    print("NODE23_REGISTRY_DATABASE_VALID")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.dsn))


if __name__ == "__main__":
    main()
