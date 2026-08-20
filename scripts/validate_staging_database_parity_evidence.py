#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
KIND = "LUMI_STAGING_DATABASE_PARITY_EVIDENCE_V1"


class DatabaseParityEvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DatabaseParityEvidenceError(message)


def load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabaseParityEvidenceError(f"unable to read evidence: {path}") from exc
    require(isinstance(payload, dict), "database parity evidence must be an object")
    return payload


def validate(
    payload: Mapping[str, Any],
    *,
    expected_git_sha: str | None = None,
    expected_version: str | None = None,
    expected_postgres_major: int | None = None,
    expected_host_sha256: str | None = None,
) -> dict[str, Any]:
    require(payload.get("schema_version") == 1, "schema_version must be 1")
    require(payload.get("kind") == KIND, "kind mismatch")
    require(payload.get("status") == "PASS" and payload.get("passed") is True, "database parity evidence must PASS")
    require(payload.get("environment") == "staging", "database parity evidence must identify staging")

    rc = payload.get("release_candidate")
    require(isinstance(rc, Mapping), "release_candidate object is missing")
    git_sha = rc.get("git_sha")
    require(isinstance(git_sha, str) and bool(SHA40.fullmatch(git_sha)), "release_candidate.git_sha must be lowercase SHA40")
    version = rc.get("version")
    require(isinstance(version, str) and bool(version.strip()), "release_candidate.version is missing")
    migration_head = rc.get("migration_head")
    require(isinstance(migration_head, str) and bool(re.fullmatch(r"[A-Za-z0-9_]+", migration_head)), "migration head is invalid")
    if expected_git_sha is not None:
        require(git_sha == expected_git_sha, "release Git SHA mismatch")
    if expected_version is not None:
        require(version == expected_version, "release version mismatch")

    database = payload.get("database")
    require(isinstance(database, Mapping), "database object is missing")
    host_hash = database.get("host_sha256")
    require(isinstance(host_hash, str) and bool(SHA256.fullmatch(host_hash)), "database host SHA-256 is invalid")
    observed_major = database.get("server_major")
    configured_major = database.get("expected_server_major")
    require(isinstance(observed_major, int) and observed_major > 0, "observed PostgreSQL major is invalid")
    require(isinstance(configured_major, int) and configured_major > 0, "expected PostgreSQL major is invalid")
    require(observed_major == configured_major, "PostgreSQL major differs from expected Staging configuration")
    versions = database.get("alembic_versions")
    require(versions == [migration_head], "database Alembic version must equal the single source migration head")
    require(database.get("transaction_read_only") is True, "database probe must execute in a read-only transaction")
    if expected_postgres_major is not None:
        require(observed_major == expected_postgres_major, "PostgreSQL major differs from collector expectation")
    if expected_host_sha256 is not None:
        require(host_hash == expected_host_sha256, "database host differs from canonical Staging target")

    checks = payload.get("checks")
    required_checks = {
        "environment_is_staging",
        "canonical_database_host",
        "alembic_metadata_drift_free",
        "alembic_single_expected_head",
        "postgres_major_matches",
        "transaction_read_only",
    }
    require(isinstance(checks, Mapping) and set(checks) == required_checks, "database parity checks shape drifted")
    require(all(checks.get(name) is True for name in required_checks), "one or more database parity checks did not PASS")
    require(isinstance(payload.get("started_at"), str) and bool(payload.get("started_at")), "started_at is missing")
    require(isinstance(payload.get("captured_at"), str) and bool(payload.get("captured_at")), "captured_at is missing")

    return {
        "status": "PASS",
        "release_git_sha": git_sha,
        "release_version": version,
        "migration_head": migration_head,
        "postgres_major": observed_major,
        "database_host_sha256": host_hash,
        "read_only": True,
        "alembic_metadata_drift_free": True,
    }


def fixture() -> dict[str, Any]:
    sha = "a" * 40
    host = "b" * 64
    return {
        "schema_version": 1,
        "kind": KIND,
        "status": "PASS",
        "release_candidate": {"git_sha": sha, "version": "1.0.0-rc", "migration_head": "0022_langgraph_postgres_runtime"},
        "environment": "staging",
        "database": {
            "host_sha256": host,
            "server_version_num": 160004,
            "server_major": 16,
            "expected_server_major": 16,
            "alembic_versions": ["0022_langgraph_postgres_runtime"],
            "transaction_read_only": True,
        },
        "checks": {
            "environment_is_staging": True,
            "canonical_database_host": True,
            "alembic_metadata_drift_free": True,
            "alembic_single_expected_head": True,
            "postgres_major_matches": True,
            "transaction_read_only": True,
        },
        "started_at": "2026-08-20T00:00:00+00:00",
        "captured_at": "2026-08-20T00:00:01+00:00",
        "passed": True,
    }


def self_test() -> dict[str, Any]:
    clean = fixture()
    validate(
        clean,
        expected_git_sha="a" * 40,
        expected_version="1.0.0-rc",
        expected_postgres_major=16,
        expected_host_sha256="b" * 64,
    )
    mutations: list[dict[str, Any]] = []
    for path, value in [
        (("status",), "BLOCK"),
        (("environment",), "production"),
        (("release_candidate", "git_sha"), "c" * 40),
        (("database", "host_sha256"), "c" * 64),
        (("database", "server_major"), 15),
        (("database", "alembic_versions"), ["old_head"]),
        (("database", "transaction_read_only"), False),
        (("checks", "alembic_metadata_drift_free"), False),
    ]:
        item = copy.deepcopy(clean)
        target: dict[str, Any] = item
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        mutations.append(item)
    blocked = 0
    for item in mutations:
        try:
            validate(
                item,
                expected_git_sha="a" * 40,
                expected_version="1.0.0-rc",
                expected_postgres_major=16,
                expected_host_sha256="b" * 64,
            )
        except DatabaseParityEvidenceError:
            blocked += 1
            continue
        raise DatabaseParityEvidenceError("negative database parity drill did not block")
    return {"status": "PASS", "negative_drills": blocked}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Production-like Staging database parity evidence")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--expected-git-sha")
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-postgres-major", type=int)
    parser.add_argument("--expected-host-sha256")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        result = self_test() if args.self_test else validate(
            load(args.evidence) if args.evidence is not None else (_ for _ in ()).throw(DatabaseParityEvidenceError("--evidence is required")),
            expected_git_sha=args.expected_git_sha,
            expected_version=args.expected_version,
            expected_postgres_major=args.expected_postgres_major,
            expected_host_sha256=args.expected_host_sha256,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except DatabaseParityEvidenceError as exc:
        raise SystemExit(f"staging database parity evidence blocked: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
