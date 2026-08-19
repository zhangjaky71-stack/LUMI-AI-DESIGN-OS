#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "scripts/production-recovery-decision.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"production recovery contract invalid: {message}")


def load_decision() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_recovery_decision", DECISION)
    require(spec is not None and spec.loader is not None, "cannot import recovery decision")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixtures() -> list[dict[str, Any]]:
    rc = {
        "git_sha": "b" * 40,
        "version": "1.0.0-rc.1",
        "migration_head": "0020_generation_operation_identity",
    }
    digest = "sha256:" + "a" * 64
    images = {
        name: f"123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/lumi-{name}@{digest}"
        for name in (
            "api",
            "agent-runtime",
            "model-gateway",
            "tool-gateway",
            "worker-media",
            "sandbox-runtime",
        )
    }
    manifest = {
        "schema_version": 1,
        "deployment_id": "prod-recovery-contract-001",
        "environment": "production",
        "release_candidate": copy.deepcopy(rc),
        "aws": {"region": "ap-northeast-1"},
        "images": images,
        "recovery": {
            "database_pitr_max_rpo_minutes": 5,
            "database_pitr_max_rto_minutes": 60,
            "object_version_recovery_required": True,
        },
    }
    baseline = {
        "schema_version": 1,
        "deployment_id": manifest["deployment_id"],
        "release_candidate": copy.deepcopy(rc),
        "passed": True,
        "services": [
            {"service_name": name, "image": image, "image_matches": True, "steady": True}
            for name, image in images.items()
        ],
    }
    rds = {
        "schema_version": 1,
        "deployment_id": manifest["deployment_id"],
        "release_candidate": copy.deepcopy(rc),
        "source_instance_id": "lumi-production-postgres",
        "recovery_instance_id": "lumi-dr-contract-001",
        "target_publicly_accessible": False,
        "source_backup_retention_days": 7,
        "observed_rpo_minutes": 4.0,
        "observed_rto_minutes": 42.0,
        "passed": True,
    }
    db = {
        "schema_version": 1,
        "release_candidate": copy.deepcopy(rc),
        "source_instance_id": rds["source_instance_id"],
        "recovery_instance_id": rds["recovery_instance_id"],
        "target_isolated": True,
        "transaction_read_only": True,
        "invariants": {"alembic_expected_head": 0, "tenant_parent_match": 0},
        "workloads": {"idempotency_ambiguous": 0, "task_expired_running": 1},
        "passed": True,
    }

    def pair(purpose: str) -> dict[str, Any]:
        checksum = ("c" if purpose == "assets" else "d") * 64
        return {
            "purpose": purpose,
            "source_region": "ap-northeast-1",
            "destination_region": "ap-southeast-1",
            "source_replication_status": "COMPLETED",
            "destination_replication_status": "REPLICA",
            "rtc_minutes": 15,
            "replication_lag_seconds": 120,
            "expected_sha256": checksum,
            "destination_sha256": checksum,
            "passed": True,
        }

    obj = {
        "schema_version": 1,
        "deployment_id": manifest["deployment_id"],
        "versioning": "Enabled",
        "expected_sha256": "e" * 64,
        "corrupt_sha256": "f" * 64,
        "restored_sha256": "e" * 64,
        "v1_version_id": "v1",
        "restored_version_id": "v3",
        "cleanup_complete": True,
        "replica_cleanup_complete": True,
        "database_evidence_versions_cleaned": True,
        "cross_region": {
            "schema_version": 1,
            "deployment_id": manifest["deployment_id"],
            "source_region": "ap-northeast-1",
            "destination_region": "ap-southeast-1",
            "rtc_minutes": 15,
            "max_replication_lag_seconds": 120,
            "pairs": [pair("assets"), pair("exports")],
            "cleanup_complete": True,
            "passed": True,
        },
        "passed": True,
    }
    cleanup = {
        "schema_version": 1,
        "deployment_id": manifest["deployment_id"],
        "recovery_instance_deleted": True,
        "database_evidence_object_deleted": True,
        "passed": True,
    }
    return [manifest, baseline, rds, db, obj, cleanup]


def evaluate(module: ModuleType, values: list[dict[str, Any]]) -> dict[str, Any]:
    return module.evaluate(
        *values,
        refs=[{"path": "reports/contract.json", "sha256": "0" * 64}],
    )


def must_block(module: ModuleType, mutate: Callable[[list[dict[str, Any]]], None], label: str) -> None:
    values = fixtures()
    mutate(values)
    require(evaluate(module, values)["passed"] is False, f"{label} must block")


def source_contract() -> None:
    object_dr = (ROOT / "infra/iac/environments/production/core/object-dr.tf").read_text()
    variables = (ROOT / "infra/iac/environments/production/core/variables.tf").read_text()
    outputs = (ROOT / "infra/iac/environments/production/core/outputs.tf").read_text()
    version_drill = (ROOT / "scripts/production-object-recovery-drill.sh").read_text()
    cross_drill = (ROOT / "scripts/production-object-cross-region-drill.sh").read_text()
    cleanup = (ROOT / "scripts/cleanup-production-object-dr-replicas.sh").read_text()
    db_verify = (ROOT / "scripts/production-recovery-db-verify.py").read_text()

    for token in (
        'object_dr_purposes = toset(["assets", "exports"])',
        'resource "aws_s3_bucket_replication_configuration" "object_dr"',
        'delete_marker_replication',
        'status = "Disabled"',
        'sse_kms_encrypted_objects',
        'replication_time',
        'metrics',
        'minutes = 15',
    ):
        require(token in object_dr, f"cross-region IaC missing {token!r}")
    require('default = "ap-southeast-1"' in variables, "launch DR region pin missing")
    require("var.object_dr_region != var.region" in variables, "DR region distinctness missing")
    require('output "object_dr_bucket_names"' in outputs, "DR bucket output missing")
    require('output "object_dr_region"' in outputs, "DR region output missing")
    require("ReplicationStatus" in cross_drill and '"REPLICA"' in cross_drill, "live replica status gate missing")
    require("replication_lag_seconds" in cross_drill and "900" in cross_drill, "live RTC lag gate missing")
    require("cleanup-production-object-dr-replicas.sh" in version_drill, "version drill replica cleanup missing")
    require("replica_cleanup_complete:true" in version_drill, "version drill cleanup evidence missing")
    require("database_evidence_versions_cleaned:true" in version_drill, "DB evidence version cleanup evidence missing")
    require("COMPLETED" in cleanup and "_node73-drill/" in cleanup, "replica cleanup fail-closed scope missing")
    require("SET TRANSACTION READ ONLY" in db_verify, "DB read-only transaction missing")
    require('"error": str(exc)' not in db_verify, "DB verifier may leak exception context")


def main() -> int:
    module = load_decision()
    source_contract()
    require(evaluate(module, fixtures())["passed"] is True, "clean recovery fixture must pass")

    must_block(module, lambda f: f[2].__setitem__("observed_rpo_minutes", 5.01), "RPO > 5m")
    must_block(module, lambda f: f[2].__setitem__("observed_rto_minutes", 60.01), "RTO > 60m")
    must_block(module, lambda f: f[2].__setitem__("recovery_instance_id", f[2]["source_instance_id"]), "source=restore")
    must_block(module, lambda f: f[2].__setitem__("target_publicly_accessible", True), "public restored RDS")
    must_block(module, lambda f: f[3]["invariants"].__setitem__("tenant_parent_match", 1), "DB invariant violation")
    must_block(module, lambda f: f[3].__setitem__("transaction_read_only", False), "writable verifier")
    must_block(module, lambda f: f[4].__setitem__("restored_sha256", "0" * 64), "version checksum mismatch")
    must_block(module, lambda f: f[4].__setitem__("replica_cleanup_complete", False), "replica cleanup incomplete")
    must_block(module, lambda f: f[4].__setitem__("database_evidence_versions_cleaned", False), "DB evidence cleanup incomplete")
    must_block(module, lambda f: f[4]["cross_region"].__setitem__("destination_region", "ap-northeast-1"), "same-region DR")
    must_block(module, lambda f: f[4]["cross_region"].__setitem__("pairs", f[4]["cross_region"]["pairs"][:1]), "missing exports CRR")
    must_block(module, lambda f: f[4]["cross_region"]["pairs"][0].__setitem__("replication_lag_seconds", 901), "CRR lag >15m")
    must_block(module, lambda f: f[4]["cross_region"]["pairs"][0].__setitem__("destination_replication_status", "PENDING"), "destination not REPLICA")
    must_block(module, lambda f: f[4]["cross_region"]["pairs"][0].__setitem__("destination_sha256", "1" * 64), "CRR checksum mismatch")
    must_block(module, lambda f: f[5].__setitem__("recovery_instance_deleted", False), "temporary RDS cleanup")
    must_block(module, lambda f: f[1]["services"][0].__setitem__("image_matches", False), "baseline runtime mismatch")

    print("production recovery contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
