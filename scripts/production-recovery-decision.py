#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_POLICY = {
    "database_pitr_max_rpo_minutes": 5,
    "database_pitr_max_rto_minutes": 60,
    "object_version_recovery_required": True,
}
RUNTIME_IMAGE_KEYS = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}
RUNTIME_SERVICE_IMAGE_KEY = {
    "api": "api",
    "agent-runtime": "agent-runtime",
    "model-gateway": "model-gateway",
    "tool-gateway": "tool-gateway",
    "worker-media": "worker-media",
    "outbox-dispatcher": "worker-media",
    "sandbox-runtime": "sandbox-runtime",
}


class RecoveryDecisionError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RecoveryDecisionError(f"{path} must contain a JSON object")
    return payload


def repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise RecoveryDecisionError(f"evidence path escapes repository: {path}") from exc


def freeze(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RecoveryDecisionError(f"evidence file missing: {path}")
    return {
        "path": repo_path(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def rc(payload: dict[str, Any]) -> tuple[Any, Any, Any]:
    value = payload.get("release_candidate")
    if not isinstance(value, dict):
        return None, None, None
    return value.get("git_sha"), value.get("version"), value.get("migration_head")


def _expected_service_images(images: object, blockers: list[str]) -> dict[str, str]:
    if not isinstance(images, dict) or set(images) != RUNTIME_IMAGE_KEYS:
        blockers.append("production manifest must contain exactly six canonical runtime images")
        return {}
    return {
        service: str(images[image_key])
        for service, image_key in RUNTIME_SERVICE_IMAGE_KEY.items()
    }


def _capacity_row_valid(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    expected = item.get("expected_desired_count")
    desired = item.get("desired_count")
    return (
        isinstance(expected, int)
        and not isinstance(expected, bool)
        and expected > 0
        and isinstance(desired, int)
        and not isinstance(desired, bool)
        and desired == expected
        and item.get("capacity_matches") is True
    )


def validate_cross_region_object_recovery(
    evidence: Any,
    *,
    deployment_id: Any,
    source_region: Any,
    blockers: list[str],
) -> tuple[Any, Any]:
    if not isinstance(evidence, dict):
        blockers.append("cross-region object recovery evidence missing")
        return None, None
    if evidence.get("schema_version") != 1 or evidence.get("passed") is not True:
        blockers.append("cross-region object recovery rehearsal is not passed=true")
    if evidence.get("deployment_id") != deployment_id:
        blockers.append("cross-region object recovery deployment_id mismatch")
    if evidence.get("source_region") != source_region:
        blockers.append("cross-region object recovery source region does not match production")
    destination_region = evidence.get("destination_region")
    if not isinstance(destination_region, str) or not destination_region or destination_region == source_region:
        blockers.append("cross-region object recovery destination must differ from source")
    if evidence.get("rtc_minutes") != 15:
        blockers.append("cross-region object recovery must use the 15-minute RTC contract")
    if evidence.get("cleanup_complete") is not True:
        blockers.append("cross-region object recovery cleanup is incomplete")

    pairs = evidence.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != 2:
        blockers.append("cross-region object recovery must verify assets and exports")
    else:
        by_purpose = {
            item.get("purpose"): item
            for item in pairs
            if isinstance(item, dict) and isinstance(item.get("purpose"), str)
        }
        if set(by_purpose) != {"assets", "exports"}:
            blockers.append("cross-region object recovery purpose set must be assets+exports")
        for purpose in ("assets", "exports"):
            item = by_purpose.get(purpose)
            if not isinstance(item, dict):
                continue
            lag = item.get("replication_lag_seconds")
            if item.get("passed") is not True:
                blockers.append(f"cross-region {purpose} replication drill is not passed=true")
            if item.get("source_region") != source_region or item.get("destination_region") != destination_region:
                blockers.append(f"cross-region {purpose} region identity mismatch")
            if item.get("source_replication_status") != "COMPLETED":
                blockers.append(f"cross-region {purpose} source replication is not COMPLETED")
            if item.get("destination_replication_status") != "REPLICA":
                blockers.append(f"cross-region {purpose} destination is not REPLICA")
            if item.get("rtc_minutes") != 15:
                blockers.append(f"cross-region {purpose} RTC contract mismatch")
            if not isinstance(lag, (int, float)) or isinstance(lag, bool) or lag < 0 or lag > 900:
                blockers.append(f"cross-region {purpose} replication lag exceeds 15 minutes")
            if item.get("expected_sha256") != item.get("destination_sha256"):
                blockers.append(f"cross-region {purpose} replica checksum mismatch")
    return destination_region, evidence.get("max_replication_lag_seconds")


def evaluate(
    manifest: dict[str, Any],
    baseline_runtime: dict[str, Any],
    rds_restore: dict[str, Any],
    database_verify: dict[str, Any],
    object_recovery: dict[str, Any],
    cleanup: dict[str, Any],
    refs: list[dict[str, str]],
) -> dict[str, Any]:
    blockers: list[str] = []
    deployment_id = manifest.get("deployment_id")
    manifest_rc = rc(manifest)

    if manifest.get("schema_version") != 1 or manifest.get("environment") != "production":
        blockers.append("manifest must be schema-v1 production")
    if manifest.get("recovery") != EXPECTED_POLICY:
        blockers.append("manifest recovery policy does not match launch policy")

    if baseline_runtime.get("schema_version") != 1 or baseline_runtime.get("passed") is not True:
        blockers.append("baseline production runtime identity is not passed=true")
    if baseline_runtime.get("deployment_id") != deployment_id:
        blockers.append("baseline production runtime deployment_id mismatch")
    if rc(baseline_runtime) != manifest_rc:
        blockers.append("baseline production runtime RC mismatch")
    services = baseline_runtime.get("services")
    expected_service_images = _expected_service_images(manifest.get("images"), blockers)
    if not isinstance(services, list) or len(services) != len(RUNTIME_SERVICE_IMAGE_KEY):
        blockers.append("baseline production runtime must contain exactly seven services")
    else:
        observed_images = {
            item.get("service_name"): item.get("image")
            for item in services
            if isinstance(item, dict) and isinstance(item.get("service_name"), str)
        }
        observed_image_keys = {
            item.get("service_name"): item.get("image_key")
            for item in services
            if isinstance(item, dict) and isinstance(item.get("service_name"), str)
        }
        if observed_images != expected_service_images:
            blockers.append(
                "baseline production seven-service image mapping does not equal manifest"
            )
        if observed_image_keys != RUNTIME_SERVICE_IMAGE_KEY:
            blockers.append("baseline production service-to-image-key mapping is not canonical")
        if any(
            not isinstance(item, dict)
            or item.get("expected_image") != expected_service_images.get(item.get("service_name"))
            or item.get("image_matches") is not True
            or not _capacity_row_valid(item)
            or item.get("steady") is not True
            for item in services
        ):
            blockers.append(
                "baseline production runtime is not fully steady or Terraform-capacity-matched"
            )

    if rds_restore.get("schema_version") != 1 or rds_restore.get("passed") is not True:
        blockers.append("RDS PITR rehearsal is not passed=true")
    if rds_restore.get("deployment_id") != deployment_id or rc(rds_restore) != manifest_rc:
        blockers.append("RDS PITR rehearsal identity mismatch")
    if rds_restore.get("source_instance_id") == rds_restore.get("recovery_instance_id"):
        blockers.append("RDS recovery instance must differ from source")
    if rds_restore.get("target_publicly_accessible") is not False:
        blockers.append("RDS recovery target must remain private")
    if rds_restore.get("source_backup_retention_days", 0) <= 0:
        blockers.append("RDS source backup retention must be positive")
    rpo = rds_restore.get("observed_rpo_minutes")
    rto = rds_restore.get("observed_rto_minutes")
    if not isinstance(rpo, (int, float)) or isinstance(rpo, bool) or rpo < 0 or rpo > 5:
        blockers.append("observed database PITR RPO exceeds 5-minute launch policy")
    if not isinstance(rto, (int, float)) or isinstance(rto, bool) or rto <= 0 or rto > 60:
        blockers.append("observed database PITR RTO exceeds 60-minute launch policy")

    if database_verify.get("schema_version") != 1 or database_verify.get("passed") is not True:
        blockers.append("isolated database verifier is not passed=true")
    if rc(database_verify) != manifest_rc:
        blockers.append("isolated database verifier RC mismatch")
    if database_verify.get("source_instance_id") != rds_restore.get("source_instance_id"):
        blockers.append("database verifier source instance mismatch")
    if database_verify.get("recovery_instance_id") != rds_restore.get("recovery_instance_id"):
        blockers.append("database verifier recovery instance mismatch")
    if database_verify.get("target_isolated") is not True:
        blockers.append("database verifier did not prove isolated target")
    if database_verify.get("transaction_read_only") is not True:
        blockers.append("database verifier did not use a read-only transaction")
    invariants = database_verify.get("invariants")
    if not isinstance(invariants, dict) or not invariants:
        blockers.append("database verifier invariants missing")
    elif any(isinstance(value, bool) or not isinstance(value, int) or value != 0 for value in invariants.values()):
        blockers.append("database verifier reported invariant violations")
    workloads = database_verify.get("workloads")
    if not isinstance(workloads, dict) or not workloads:
        blockers.append("database recovery workload inventory missing")

    if object_recovery.get("schema_version") != 1 or object_recovery.get("passed") is not True:
        blockers.append("object version recovery rehearsal is not passed=true")
    if object_recovery.get("deployment_id") != deployment_id:
        blockers.append("object recovery deployment_id mismatch")
    if object_recovery.get("versioning") != "Enabled":
        blockers.append("object recovery requires versioning=Enabled")
    if object_recovery.get("cleanup_complete") is not True:
        blockers.append("object recovery drill cleanup is incomplete")
    if object_recovery.get("replica_cleanup_complete") is not True:
        blockers.append("object version recovery replica cleanup is incomplete")
    if object_recovery.get("database_evidence_versions_cleaned") is not True:
        blockers.append("database recovery evidence data-version cleanup is incomplete")
    if object_recovery.get("expected_sha256") != object_recovery.get("restored_sha256"):
        blockers.append("object recovery restored checksum mismatch")
    if object_recovery.get("expected_sha256") == object_recovery.get("corrupt_sha256"):
        blockers.append("object recovery corruption fixture did not differ from v1")
    if object_recovery.get("v1_version_id") == object_recovery.get("restored_version_id"):
        blockers.append("object recovery must restore v1 as a new current version")

    manifest_aws = manifest.get("aws")
    source_region = manifest_aws.get("region") if isinstance(manifest_aws, dict) else None
    destination_region, max_object_lag = validate_cross_region_object_recovery(
        object_recovery.get("cross_region"),
        deployment_id=deployment_id,
        source_region=source_region,
        blockers=blockers,
    )

    if cleanup.get("schema_version") != 1 or cleanup.get("passed") is not True:
        blockers.append("DR cleanup evidence is not passed=true")
    if cleanup.get("deployment_id") != deployment_id:
        blockers.append("DR cleanup deployment_id mismatch")
    if cleanup.get("recovery_instance_deleted") is not True:
        blockers.append("temporary RDS recovery instance was not deleted")
    if cleanup.get("database_evidence_object_deleted") is not True:
        blockers.append("temporary database evidence current object was not deleted")
    source_versions_remaining = cleanup.get("database_evidence_source_versions_remaining")
    recovery_versions_remaining = cleanup.get("database_evidence_recovery_versions_remaining")
    if (
        isinstance(source_versions_remaining, bool)
        or not isinstance(source_versions_remaining, int)
        or source_versions_remaining != 0
    ):
        blockers.append("database recovery evidence source versions/delete-markers remain")
    if (
        isinstance(recovery_versions_remaining, bool)
        or not isinstance(recovery_versions_remaining, int)
        or recovery_versions_remaining != 0
    ):
        blockers.append("database recovery evidence recovery-region versions/delete-markers remain")
    if cleanup.get("source_region") != source_region:
        blockers.append("DR cleanup source region mismatch")
    if cleanup.get("recovery_region") != destination_region:
        blockers.append("DR cleanup recovery region mismatch")

    blockers = sorted(set(blockers))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "deployment_id": deployment_id,
        "release_candidate": manifest.get("release_candidate", {}),
        "recovery_policy": manifest.get("recovery", {}),
        "observed_rpo_minutes": rpo,
        "observed_rto_minutes": rto,
        "object_dr_destination_region": destination_region,
        "object_dr_max_replication_lag_seconds": max_object_lag,
        "database_evidence_source_versions_remaining": source_versions_remaining,
        "database_evidence_recovery_versions_remaining": recovery_versions_remaining,
        "passed": not blockers,
        "evidence_refs": refs,
        "blockers": blockers,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["decision_id"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize NODE-68/73 production-like recovery decision")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--baseline-runtime", required=True)
    parser.add_argument("--rds-restore", required=True)
    parser.add_argument("--database-verify", required=True)
    parser.add_argument("--object-recovery", required=True)
    parser.add_argument("--cleanup", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    paths = [
        Path(args.baseline_runtime),
        Path(args.rds_restore),
        Path(args.database_verify),
        Path(args.object_recovery),
        Path(args.cleanup),
    ]
    try:
        result = evaluate(
            load_json(Path(args.manifest)),
            load_json(paths[0]),
            load_json(paths[1]),
            load_json(paths[2]),
            load_json(paths[3]),
            load_json(paths[4]),
            [freeze(path) for path in paths],
        )
    except (OSError, json.JSONDecodeError, RecoveryDecisionError) as exc:
        raise SystemExit(f"production recovery decision invalid: {exc}") from exc

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if result["passed"] else "BLOCK", "decision_id": result["decision_id"]}, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
