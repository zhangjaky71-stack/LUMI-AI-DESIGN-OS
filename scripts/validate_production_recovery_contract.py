#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "scripts" / "production-recovery-decision.py"


def load_decision() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_production_recovery_decision", DECISION_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to import production recovery decision")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"production recovery contract invalid: {message}")


def manifest() -> dict[str, Any]:
    digest = "sha256:" + "a" * 64
    return {
        "schema_version": 1,
        "deployment_id": "prod-recovery-contract-001",
        "environment": "production",
        "release_candidate": {
            "git_sha": "b" * 40,
            "version": "1.0.0-rc.1",
            "migration_head": "0020_generation_operation_identity",
        },
        "aws": {"region": "ap-northeast-1"},
        "images": {
            name: f"123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/lumi-{name}@{digest}"
            for name in (
                "api",
                "agent-runtime",
                "model-gateway",
                "tool-gateway",
                "worker-media",
                "sandbox-runtime",
            )
        },
        "recovery": {
            "database_pitr_max_rpo_minutes": 5,
            "database_pitr_max_rto_minutes": 60,
            "object_version_recovery_required": True,
        },
    }


def baseline(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "deployment_id": m["deployment_id"],
        "release_candidate": copy.deepcopy(m["release_candidate"]),
        "passed": True,
        "services": [
            {
                "service_name": name,
                "image": image,
                "image_matches": True,
                "steady": True,
            }
            for name, image in m["images"].items()
        ],
    }


def rds(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "deployment_id": m["deployment_id"],
        "release_candidate": copy.deepcopy(m["release_candidate"]),
        "source_instance_id": "lumi-production-postgres",
        "recovery_instance_id": "lumi-dr-contract-001",
        "target_publicly_accessible": False,
        "source_backup_retention_days": 7,
        "observed_rpo_minutes": 4.0,
        "observed_rto_minutes": 42.0,
        "passed": True,
    }


def database_verify(m: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "release_candidate": copy.deepcopy(m["release_candidate"]),
        "source_instance_id": r["source_instance_id"],
        "recovery_instance_id": r["recovery_instance_id"],
        "target_isolated": True,
        "transaction_read_only": True,
        "invariants": {"alembic_expected_head": 0, "tenant_parent_match": 0},
        "workloads": {"idempotency_ambiguous": 0, "task_expired_running": 1},
        "passed": True,
    }


def pair(purpose: str) -> dict[str, Any]:
    checksum = "c" * 64 if purpose == "assets" else "d" * 64
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


def object_recovery(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "deployment_id": m["deployment_id"],
        "versioning": "Enabled",
        "expected_sha256": "e" * 64,
        "corrupt_sha256": "f" * 64,
        "restored_sha256": "e" * 64,
        "v1_version_id": "v1",
        "restored_version_id": "v3",
        "cleanup_complete": True,
        "replica_cleanup_complete": True,
        "cross_region": {
            "schema_version": 1,
            "deployment_id": m["deployment_id"],
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


def cleanup(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "deployment_id": m["deployment_id"],
        "recovery_instance_deleted": True,
        "database_evidence_object_deleted": True,
        "passed": True,
    }


def evaluate(module: ModuleType, fixtures: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    m, b, r, db, obj, clean = fixtures
    return module.evaluate(m, b, r, db, obj, clean, refs=[{"path": "reports/contract.json", "sha256": "0" * 64}])


def fresh() -> tuple[dict[str, Any], ...]:
    m = manifest()
    r = rds(m)
    return m, baseline(m), r, database_verify(m, r), object_recovery(m), cleanup(m)


def must_block(module: ModuleType, mutate: Any, label: str) -> None:
    fixtures = fresh()
    mutate(fixtures)
    require(evaluate(module, fixtures)["passed"] is False, f"{label} must block")


def validate_source_contract() -> None:
    object_dr = (ROOT / "infra/iac/environments/production/core/object-dr.tf").read_text(encoding="utf-8")
    object_dr_vars = (ROOT / "infra/iac/environments/production/core/variables.tf").read_text(encoding="utf-8")
    object_dr_outputs = (ROOT / "infra/iac/environments/production/core/outputs.tf").read_text(encoding="utf-8")
    version_drill = (ROOT / "scripts/production-object-recovery-drill.sh").read_text(encoding="utf-8")
    cross_drill = (ROOT / "scripts/production-object-cross-region-drill.sh").read_text(encoding="utf-8")
    replica_cleanup = (ROOT / "scripts/cleanup-production-object-dr-replicas.sh").read_text(encoding="utf-8")
    db_verify = (ROOT / "scripts/production-recovery-db-verify.py").read_text(encoding="utf-8")

    for token in (
        'local.object_dr_purposes = toset(["assets", "exports"])',
        'resource "aws_s3_bucket_replication_configuration" "object_dr"',
        'status = "Disabled"',
        'sse_kms_encrypted_objects',
        'replication_time',
        'minutes = 15',
        'metrics',
    ):
        require(token in object_dr, f"cross-region IaC missing {token!r}")
    require('default = "ap-southeast-1"' in object_dr_vars, "launch DR region pin missing")
    require("var.object_dr_region != var.region" in object_dr_vars, "DR region distinctness validation missing")
    require('output "object_dr_bucket_names"' in object_dr_outputs, "DR bucket output missing")
    require('output "object_dr_region"' in object_dr_outputs, "DR region output missing")
    require("ReplicationStatus" in cross_drill and '"REPLICA"' in cross_drill, "live replica-status probe missing")
    require("replication_lag_seconds" in cross_drill and "900" in cross_drill, "15-minute live lag gate missing")
    require("cleanup-production-object-dr-replicas.sh" in version_drill, "version drill does not clean replicas")
    require("COMPLETED" in replica_cleanup, "replica cleanup does not wait for completed replication")
    require("SET TRANSACTION READ ONLY" in db_verify, "DB verifier read-only transaction missing")
    require('"error": str(exc)' not in db_verify, "DB verifier may serialize exception details")


def main() -> int:
    module = load_decision()
    validate_source_contract()

    clean = fresh()
    require(evaluate(module, clean)["passed"] is True, "clean production recovery fixture must pass")

    must_block(module, lambda f: f[2].__setitem__("observed_rpo_minutes", 5.01), "RPO > 5m")
    must_block(module, lambda f: f[2].__setitem__("observed_rto_minutes", 60.01), "RTO > 60m")
    must_block(module, lambda f: f[2].__setitem__("recovery_instance_id", f[2]["source_instance_id"]), "same RDS source/restore")
    must_block(module, lambda f: f[2].__setitem__("target_publicly_accessible", True), "public restored RDS")
    must_block(module, lambda f: f[3]["invariants"].__setitem__("tenant_parent_match", 1), "DB invariant violation")
    must_block(module, lambda f: f[3].__setitem__("transaction_read_only", False), "writable recovery verifier")
    must_block(module, lambda f: f[4].__setitem__("restored_sha256", "0" * 64), "version restore checksum mismatch")
    must_block(module, lambda f: f[4].__setitem__("replica_cleanup_complete", False), "replica cleanup incomplete")
    must_block(module, lambda f: f[4]["cross_region"].__setitem__("destination_region", "ap-northeast-1"), "same-region DR destination")
    must_block(module, lambda f: f[4]["cross_region"].__setitem__("pairs", [pair("assets")]), "missing exports CRR")
    must_block(module, lambda f: f[4]["cross_region"]["pairs"][0].__setitem__("replication_lag_seconds", 901), "CRR lag > 15m")
    must_block(module, lambda f: f[4]["cross_region"]["pairs"][0].__setitem__("destination_replication_status", "PENDING"), "destination not REPLICA")
    must_block(module, lambda f: f[4]["cross_region"]["pairs"][0].__setitem__("destination_sha256", "1" * 64), "CRR checksum mismatch")
    must_block(module, lambda f: f[5].__setitem__("recovery_instance_deleted", False), "temporary RDS cleanup incomplete")
    must_block(module, lambda f: f[1]["services"][0].__setitem__("image_matches", False), "baseline runtime image mismatch")

    print("production recovery contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
