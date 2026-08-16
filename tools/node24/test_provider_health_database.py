from __future__ import annotations

import argparse
import asyncio
import time

from lumi_model_gateway.provider_health import (
    ProviderHealthAuditEvent,
    ProviderHealthSnapshot,
    ProviderHealthState,
)
from lumi_model_gateway.provider_health_postgres import (
    PostgresProviderHealthPersistence,
)


async def require_schema(connection: object) -> None:
    fetchval = getattr(connection, "fetchval")
    for table in (
        "provider_health_summaries",
        "provider_health_override_audit",
    ):
        exists = await fetchval("SELECT to_regclass($1)", f"public.{table}")
        if exists != table:
            raise AssertionError(f"missing NODE-24 table: {table}")
    trigger_count = await fetchval(
        """
        SELECT count(*)
        FROM pg_trigger
        WHERE tgname = 'trg_provider_health_override_audit_immutable'
          AND NOT tgisinternal
        """
    )
    if int(trigger_count or 0) != 1:
        raise AssertionError("provider health audit immutable trigger missing")


async def require_runtime_grants(connection: object) -> None:
    fetchval = getattr(connection, "fetchval")
    role_exists = await fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app')"
    )
    if not role_exists:
        return
    for table in (
        "provider_health_summaries",
        "provider_health_override_audit",
    ):
        select_ok = await fetchval(
            "SELECT has_table_privilege('lumi_app', $1, 'SELECT')",
            table,
        )
        insert_ok = await fetchval(
            "SELECT has_table_privilege('lumi_app', $1, 'INSERT')",
            table,
        )
        update_ok = await fetchval(
            "SELECT has_table_privilege('lumi_app', $1, 'UPDATE')",
            table,
        )
        delete_ok = await fetchval(
            "SELECT has_table_privilege('lumi_app', $1, 'DELETE')",
            table,
        )
        if select_ok is not True or insert_ok is not True:
            raise AssertionError(f"lumi_app missing health read/append grant: {table}")
        if update_ok is True or delete_ok is True:
            raise AssertionError(f"lumi_app health history is not append-only: {table}")


async def require_append_only_persistence(connection: object) -> None:
    execute = getattr(connection, "execute")
    persistence = PostgresProviderHealthPersistence()
    observed = time.time()
    snapshot = ProviderHealthSnapshot(
        provider="provider-a",
        model="model-a",
        capability="llm.reasoning",
        state=ProviderHealthState.DEGRADED,
        score=60,
        sample_count=10,
        success_rate=0.8,
        failure_rate=0.2,
        rate_limit_rate=0.1,
        timeout_rate=0.1,
        latency_p50_ms=120,
        latency_p95_ms=900,
        queue_completion_p95_ms=None,
        consecutive_failures=1,
        open_until_epoch=None,
        recovering_inflight=0,
        recovering_successes=0,
        capacity_hint=None,
        updated_at_epoch=observed,
        reason="failure_rate_degraded",
    )
    summary_id = await persistence.append_summary(
        connection,  # type: ignore[arg-type]
        snapshot,
        source_instance="node24-ci",
    )
    audit = ProviderHealthAuditEvent(
        action="force_degraded",
        provider="provider-a",
        model="model-a",
        capability="llm.reasoning",
        actor_id="node24-ci-admin",
        reason="failure injection",
        observed_at_epoch=observed,
        expires_at_epoch=observed + 300,
    )
    audit_id = await persistence.append_audit(
        connection,  # type: ignore[arg-type]
        audit,
    )

    fetchval = getattr(connection, "fetchval")
    summary_count = await fetchval(
        "SELECT count(*) FROM provider_health_summaries WHERE id = $1::uuid",
        summary_id,
    )
    audit_count = await fetchval(
        "SELECT count(*) FROM provider_health_override_audit WHERE id = $1::uuid",
        audit_id,
    )
    if int(summary_count or 0) != 1 or int(audit_count or 0) != 1:
        raise AssertionError("provider health append persistence failed")

    try:
        await execute(
            "UPDATE provider_health_override_audit SET reason = 'mutated' "
            "WHERE id = $1::uuid",
            audit_id,
        )
    except Exception as exc:
        if "append-only" not in str(exc):
            raise
    else:
        raise AssertionError("provider health audit UPDATE was accepted")

    try:
        await execute(
            "DELETE FROM provider_health_override_audit WHERE id = $1::uuid",
            audit_id,
        )
    except Exception as exc:
        if "append-only" not in str(exc):
            raise
    else:
        raise AssertionError("provider health audit DELETE was accepted")


async def run(dsn: str) -> None:
    try:
        import asyncpg
    except ImportError as exc:
        raise RuntimeError(
            "asyncpg is required for NODE-24 PostgreSQL verification"
        ) from exc
    connection = await asyncpg.connect(dsn)
    try:
        await require_schema(connection)
        await require_runtime_grants(connection)
        await require_append_only_persistence(connection)
    finally:
        await connection.close()
    print("NODE24_PROVIDER_HEALTH_DATABASE_VALID")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.dsn))


if __name__ == "__main__":
    main()
