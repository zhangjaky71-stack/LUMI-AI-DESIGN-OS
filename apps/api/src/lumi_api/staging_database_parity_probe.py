from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MARKER = "LUMI_STAGING_DB_PARITY="


class StagingDatabaseParityError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StagingDatabaseParityError(message)


def migration_url() -> str:
    raw = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    require(bool(raw), "MIGRATION_DATABASE_URL is required")
    url = make_url(raw)
    require(url.drivername in {"postgresql+asyncpg", "postgres+asyncpg"}, "migration URL must use asyncpg")
    require(bool(url.host), "migration URL host is missing")
    return raw


def source_migration_head() -> str:
    result = subprocess.run(
        ["alembic", "-c", "apps/api/alembic.ini", "heads"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    require(result.returncode == 0, "unable to resolve source Alembic head")
    heads: list[str] = []
    for line in result.stdout.splitlines():
        token = line.strip().split(" ", 1)[0].strip()
        if token and re.fullmatch(r"[A-Za-z0-9_]+", token):
            heads.append(token)
    require(len(heads) == 1, "source must expose exactly one Alembic head")
    return heads[0]


def require_alembic_no_drift() -> None:
    result = subprocess.run(
        ["alembic", "-c", "apps/api/alembic.ini", "check"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    require(result.returncode == 0, "Alembic metadata/database drift check failed")


async def collect(*, release_git_sha: str, release_version: str, expected_postgres_major: int, expected_host_sha256: str) -> dict[str, Any]:
    require(os.environ.get("LUMI_ENV") == "staging", "LUMI_ENV must equal staging")
    require(bool(SHA40.fullmatch(release_git_sha)), "release Git SHA must be lowercase SHA40")
    require(bool(release_version.strip()), "release version is required")
    require(expected_postgres_major > 0, "expected PostgreSQL major must be positive")
    require(bool(SHA256.fullmatch(expected_host_sha256)), "expected host SHA-256 is invalid")

    raw_url = migration_url()
    url = make_url(raw_url)
    host_hash = hashlib.sha256(str(url.host).lower().rstrip(".").encode("utf-8")).hexdigest()
    require(host_hash == expected_host_sha256, "migration secret does not target canonical Staging PostgreSQL host")

    migration_head = source_migration_head()
    require_alembic_no_drift()

    engine = create_async_engine(raw_url, pool_pre_ping=True)
    started = datetime.now(UTC)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                read_only = str((await connection.execute(text("SHOW transaction_read_only"))).scalar_one()).lower() == "on"
                server_version_num = int((await connection.execute(text("SHOW server_version_num"))).scalar_one())
                observed_major = server_version_num // 10000
                versions = [
                    str(item)
                    for item in (
                        await connection.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
                    ).scalars().all()
                ]
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()

    checks = {
        "environment_is_staging": True,
        "canonical_database_host": host_hash == expected_host_sha256,
        "alembic_metadata_drift_free": True,
        "alembic_single_expected_head": versions == [migration_head],
        "postgres_major_matches": observed_major == expected_postgres_major,
        "transaction_read_only": read_only,
    }
    passed = all(checks.values())
    finished = datetime.now(UTC)
    return {
        "schema_version": 1,
        "kind": "LUMI_STAGING_DATABASE_PARITY_EVIDENCE_V1",
        "status": "PASS" if passed else "BLOCK",
        "release_candidate": {
            "git_sha": release_git_sha,
            "version": release_version,
            "migration_head": migration_head,
        },
        "environment": "staging",
        "database": {
            "host_sha256": host_hash,
            "server_version_num": server_version_num,
            "server_major": observed_major,
            "expected_server_major": expected_postgres_major,
            "alembic_versions": versions,
            "transaction_read_only": read_only,
        },
        "checks": checks,
        "started_at": started.isoformat(),
        "captured_at": finished.isoformat(),
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Production-like Staging PostgreSQL parity probe")
    parser.add_argument("--release-git-sha", required=True)
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--expected-postgres-major", required=True, type=int)
    parser.add_argument("--expected-host-sha256", required=True)
    args = parser.parse_args()
    try:
        payload = asyncio.run(
            collect(
                release_git_sha=args.release_git_sha,
                release_version=args.release_version,
                expected_postgres_major=args.expected_postgres_major,
                expected_host_sha256=args.expected_host_sha256,
            )
        )
        print(MARKER + json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return 0 if payload["passed"] else 2
    except Exception as exc:
        # Never serialize DB/library exception text: it may contain endpoint or credential-adjacent context.
        print(
            MARKER
            + json.dumps(
                {
                    "schema_version": 1,
                    "kind": "LUMI_STAGING_DATABASE_PARITY_EVIDENCE_V1",
                    "status": "BLOCK",
                    "passed": False,
                    "error_type": type(exc).__name__,
                    "error": "staging database parity probe failed; inspect protected task logs",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
