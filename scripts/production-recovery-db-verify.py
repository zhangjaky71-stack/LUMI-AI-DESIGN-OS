#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

INVARIANTS: tuple[tuple[str, str], ...] = (
    (
        "project_workspace_tenant_match",
        """SELECT count(*) FROM projects p JOIN workspaces w ON w.id = p.workspace_id WHERE p.organization_id <> w.organization_id""",
    ),
    (
        "asset_project_tenant_match",
        """SELECT count(*) FROM assets a JOIN projects p ON p.id = a.project_id WHERE a.project_id IS NOT NULL AND a.organization_id <> p.organization_id""",
    ),
    (
        "asset_file_parent_tenant_match",
        """SELECT count(*) FROM asset_files af JOIN assets a ON a.id = af.asset_id WHERE af.organization_id <> a.organization_id""",
    ),
    (
        "artifact_version_parent_tenant_match",
        """SELECT count(*) FROM artifact_versions av JOIN artifacts a ON a.id = av.artifact_id WHERE av.organization_id <> a.organization_id OR av.project_id <> a.project_id""",
    ),
    (
        "artifact_file_parent_tenant_match",
        """SELECT count(*) FROM artifact_files af JOIN artifact_versions av ON av.id = af.artifact_version_id WHERE af.organization_id <> av.organization_id""",
    ),
    (
        "agent_run_control_parent_match",
        """SELECT count(*) FROM agent_run_control arc JOIN agent_runs ar ON ar.id = arc.agent_run_id WHERE arc.organization_id <> ar.organization_id OR arc.project_id <> ar.project_id""",
    ),
    (
        "task_agent_run_parent_match",
        """SELECT count(*) FROM tasks t JOIN agent_runs ar ON ar.id = t.agent_run_id WHERE t.agent_run_id IS NOT NULL AND (t.organization_id <> ar.organization_id OR t.project_id <> ar.project_id)""",
    ),
    (
        "cost_ledger_duplicate_operation_entry",
        """SELECT count(*) FROM (SELECT operation_id, entry_type FROM cost_ledger WHERE operation_id IS NOT NULL GROUP BY operation_id, entry_type HAVING count(*) > 1) duplicates""",
    ),
    (
        "asset_file_checksum_format",
        """SELECT count(*) FROM asset_files WHERE checksum_sha256 !~ '^[0-9a-fA-F]{64}$'""",
    ),
    (
        "artifact_file_checksum_format",
        """SELECT count(*) FROM artifact_files WHERE checksum_sha256 !~ '^[0-9a-fA-F]{64}$'""",
    ),
)

WORKLOADS: tuple[tuple[str, str], ...] = (
    ("outbox_unpublished", "SELECT count(*) FROM outbox_events WHERE published_at IS NULL"),
    ("dead_letter_unreplayed", "SELECT count(*) FROM dead_letter_records WHERE replayed_at IS NULL"),
    ("idempotency_ambiguous", "SELECT count(*) FROM idempotency_operations WHERE status = 'ambiguous'"),
    (
        "idempotency_expired_in_progress",
        "SELECT count(*) FROM idempotency_operations WHERE status = 'in_progress' AND lease_expires_at IS NOT NULL AND lease_expires_at < now()",
    ),
    (
        "task_expired_running",
        "SELECT count(*) FROM tasks WHERE status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < now()",
    ),
    (
        "agent_control_non_terminal",
        "SELECT count(*) FROM agent_run_control WHERE control_status IN ('pending','running','interrupted')",
    ),
    ("asset_object_refs", "SELECT count(*) FROM asset_files"),
    ("artifact_object_refs", "SELECT count(*) FROM artifact_files"),
    ("cost_ledger_entries", "SELECT count(*) FROM cost_ledger"),
)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def recovery_url() -> str:
    raw = required_env("LUMI_DATABASE_URL")
    host = required_env("LUMI_RECOVERY_HOST")
    primary_host = required_env("LUMI_RECOVERY_PRIMARY_HOST")
    if os.environ.get("LUMI_RECOVERY_VERIFY_ISOLATED") != "1":
        raise RuntimeError("LUMI_RECOVERY_VERIFY_ISOLATED=1 is required")
    if host.lower().rstrip(".") == primary_host.lower().rstrip("."):
        raise RuntimeError("recovery endpoint must differ from production primary endpoint")
    port = int(os.environ.get("LUMI_RECOVERY_PORT", "5432"))
    if port != 5432:
        raise RuntimeError("production RDS recovery endpoint must use PostgreSQL port 5432")
    url = make_url(raw)
    if url.drivername not in {"postgresql+asyncpg", "postgres+asyncpg"}:
        raise RuntimeError("LUMI_DATABASE_URL must use the asyncpg SQLAlchemy driver")
    return url.set(host=host, port=port).render_as_string(hide_password=False)


async def scalar_int(connection: Any, sql: str) -> int:
    value = (await connection.execute(text(sql))).scalar_one()
    return int(value)


async def verify() -> dict[str, Any]:
    started = datetime.now(UTC)
    expected_head = required_env("LUMI_EXPECTED_MIGRATION_HEAD")
    database_url = recovery_url()
    engine = create_async_engine(database_url, pool_pre_ping=True)
    invariant_results: dict[str, int] = {}
    workload_results: dict[str, int] = {}
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                version_rows = (
                    await connection.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
                ).scalars().all()
                versions = [str(item) for item in version_rows]
                invariant_results["alembic_single_version"] = 0 if len(versions) == 1 else abs(len(versions) - 1)
                invariant_results["alembic_expected_head"] = 0 if versions == [expected_head] else 1
                for name, sql in INVARIANTS:
                    invariant_results[name] = await scalar_int(connection, sql)
                for name, sql in WORKLOADS:
                    workload_results[name] = await scalar_int(connection, sql)
                server_time = (await connection.execute(text("SELECT now()"))).scalar_one()
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()

    finished = datetime.now(UTC)
    passed = all(value == 0 for value in invariant_results.values())
    return {
        "schema_version": 1,
        "recovery_instance_id": required_env("LUMI_RECOVERY_INSTANCE_ID"),
        "source_instance_id": required_env("LUMI_RECOVERY_SOURCE_INSTANCE_ID"),
        "release_candidate": {
            "git_sha": required_env("LUMI_RECOVERY_GIT_SHA"),
            "version": required_env("LUMI_RECOVERY_VERSION"),
            "migration_head": expected_head,
        },
        "target_isolated": True,
        "transaction_read_only": True,
        "database_host_sha256": hashlib.sha256(required_env("LUMI_RECOVERY_HOST").encode()).hexdigest(),
        "server_time": server_time.isoformat() if hasattr(server_time, "isoformat") else str(server_time),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "invariants": invariant_results,
        "workloads": workload_results,
        "passed": passed,
    }


def upload_evidence(payload: dict[str, Any]) -> dict[str, str]:
    bucket = required_env("LUMI_RECOVERY_EVIDENCE_BUCKET")
    key = required_env("LUMI_RECOVERY_EVIDENCE_KEY")
    if not key.startswith("recovery-evidence/v1/") or ".." in key or key.startswith("/"):
        raise RuntimeError("recovery evidence key must stay below recovery-evidence/v1/")
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksum = hashlib.sha256(body).hexdigest()
    client = boto3.client("s3", region_name=os.environ.get("AWS_REGION"))
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        Metadata={"sha256": checksum, "purpose": "lumi-production-dr-rehearsal"},
    )
    return {"bucket": bucket, "key": key, "sha256": checksum}


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only verifier for an isolated Production RDS recovery target")
    parser.add_argument("--output", default="/tmp/lumi-production-recovery-db.json")
    args = parser.parse_args()
    try:
        payload = asyncio.run(verify())
        evidence = upload_evidence(payload)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({**payload, "evidence_object": evidence}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "PASS" if payload["passed"] else "BLOCK", "evidence_sha256": evidence["sha256"]}, sort_keys=True))
        return 0 if payload["passed"] else 2
    except Exception as exc:
        # Exception strings from DB/AWS libraries can contain connection endpoints,
        # request context, or credential-adjacent values. Never serialize them.
        print(
            json.dumps(
                {
                    "status": "BLOCK",
                    "error_type": type(exc).__name__,
                    "error": "production recovery verifier failed; inspect protected service logs",
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
