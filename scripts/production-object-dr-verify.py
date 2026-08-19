#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

CRITICAL_BUCKETS = ("assets", "exports")
DRILL_PREFIX = "_node73-drill/"


class ObjectDrError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_aws(
    *args: str,
    region: str | None = None,
    expect_json: bool = True,
    check: bool = True,
) -> Any:
    command = ["aws"]
    if region:
        command.extend(["--region", region])
    command.extend(args)
    if expect_json:
        command.extend(["--output", "json"])
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if check and proc.returncode != 0:
        stderr = proc.stderr.strip()
        raise ObjectDrError(f"AWS command failed ({' '.join(command[:4])} ...): {stderr[:500]}")
    if not expect_json:
        return proc
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ObjectDrError("AWS command returned invalid JSON") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def normalize_kms(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def list_current_objects(bucket: str, region: str) -> list[dict[str, Any]]:
    payload = run_aws("s3api", "list-objects-v2", "--bucket", bucket, region=region)
    contents = payload.get("Contents", []) if isinstance(payload, dict) else []
    if not isinstance(contents, list):
        raise ObjectDrError(f"invalid list-objects-v2 response for {bucket}")
    return [item for item in contents if isinstance(item, dict)]


def list_versions(bucket: str, key: str, region: str) -> list[dict[str, str]]:
    payload = run_aws(
        "s3api",
        "list-object-versions",
        "--bucket",
        bucket,
        "--prefix",
        key,
        region=region,
    )
    result: list[dict[str, str]] = []
    for collection in ("Versions", "DeleteMarkers"):
        values = payload.get(collection, []) if isinstance(payload, dict) else []
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict) or item.get("Key") != key:
                continue
            version_id = item.get("VersionId")
            if isinstance(version_id, str) and version_id:
                result.append({"Key": key, "VersionId": version_id})
    return result


def delete_all_versions(bucket: str, key: str, region: str) -> bool:
    objects = list_versions(bucket, key, region)
    if objects:
        payload = json.dumps({"Objects": objects, "Quiet": True}, separators=(",", ":"))
        run_aws(
            "s3api",
            "delete-objects",
            "--bucket",
            bucket,
            "--delete",
            payload,
            region=region,
        )
    return not list_versions(bucket, key, region)


def verify_bucket_config(
    purpose: str,
    source_bucket: str,
    destination_bucket: str,
    source_region: str,
    destination_region: str,
    destination_kms_key_arn: str,
) -> dict[str, Any]:
    blockers: list[str] = []

    source_versioning = run_aws(
        "s3api", "get-bucket-versioning", "--bucket", source_bucket, region=source_region
    )
    destination_versioning = run_aws(
        "s3api", "get-bucket-versioning", "--bucket", destination_bucket, region=destination_region
    )
    if source_versioning.get("Status") != "Enabled":
        blockers.append("source versioning is not Enabled")
    if destination_versioning.get("Status") != "Enabled":
        blockers.append("destination versioning is not Enabled")

    replication = run_aws(
        "s3api", "get-bucket-replication", "--bucket", source_bucket, region=source_region
    )
    config = replication.get("ReplicationConfiguration", {}) if isinstance(replication, dict) else {}
    rules = config.get("Rules", []) if isinstance(config, dict) else []
    enabled_rules = [rule for rule in rules if isinstance(rule, dict) and rule.get("Status") == "Enabled"]
    expected_destination_arn = f"arn:aws:s3:::{destination_bucket}"
    matching = [
        rule
        for rule in enabled_rules
        if isinstance(rule.get("Destination"), dict)
        and rule["Destination"].get("Bucket") == expected_destination_arn
    ]
    if len(matching) != 1:
        blockers.append("expected exactly one enabled replication rule to DR bucket")
        rule: dict[str, Any] = {}
    else:
        rule = matching[0]

    destination = rule.get("Destination", {}) if isinstance(rule, dict) else {}
    metrics = destination.get("Metrics", {}) if isinstance(destination, dict) else {}
    replication_time = destination.get("ReplicationTime", {}) if isinstance(destination, dict) else {}
    encryption = destination.get("EncryptionConfiguration", {}) if isinstance(destination, dict) else {}
    source_selection = rule.get("SourceSelectionCriteria", {}) if isinstance(rule, dict) else {}
    sse_kms = source_selection.get("SseKmsEncryptedObjects", {}) if isinstance(source_selection, dict) else {}
    delete_markers = rule.get("DeleteMarkerReplication", {}) if isinstance(rule, dict) else {}

    if metrics.get("Status") != "Enabled" or (metrics.get("EventThreshold") or {}).get("Minutes") != 15:
        blockers.append("replication metrics must be Enabled with 15-minute threshold")
    if replication_time.get("Status") != "Enabled" or (replication_time.get("Time") or {}).get("Minutes") != 15:
        blockers.append("S3 RTC must be Enabled with 15-minute target")
    if delete_markers.get("Status") != "Enabled":
        blockers.append("delete-marker replication is not Enabled")
    if sse_kms.get("Status") != "Enabled":
        blockers.append("SSE-KMS source selection is not Enabled")
    if normalize_kms(encryption.get("ReplicaKmsKeyID")) != destination_kms_key_arn:
        blockers.append("replication destination KMS key does not match canonical DR key")

    destination_encryption = run_aws(
        "s3api",
        "get-bucket-encryption",
        "--bucket",
        destination_bucket,
        region=destination_region,
    )
    ruleset = (
        destination_encryption.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        if isinstance(destination_encryption, dict)
        else []
    )
    default = {}
    if isinstance(ruleset, list) and ruleset and isinstance(ruleset[0], dict):
        default = ruleset[0].get("ApplyServerSideEncryptionByDefault", {}) or {}
    if default.get("SSEAlgorithm") != "aws:kms":
        blockers.append("destination bucket default encryption is not aws:kms")
    if normalize_kms(default.get("KMSMasterKeyID")) != destination_kms_key_arn:
        blockers.append("destination bucket KMS key does not match canonical DR key")

    return {
        "purpose": purpose,
        "source_bucket": source_bucket,
        "destination_bucket": destination_bucket,
        "source_versioning": source_versioning.get("Status"),
        "destination_versioning": destination_versioning.get("Status"),
        "replication_rule_count": len(matching),
        "rtc_status": replication_time.get("Status"),
        "rtc_minutes": (replication_time.get("Time") or {}).get("Minutes"),
        "metrics_status": metrics.get("Status"),
        "metrics_minutes": (metrics.get("EventThreshold") or {}).get("Minutes"),
        "delete_marker_replication": delete_markers.get("Status"),
        "sse_kms_source_selection": sse_kms.get("Status"),
        "destination_kms_key_arn": normalize_kms(encryption.get("ReplicaKmsKeyID")),
        "destination_default_encryption": default.get("SSEAlgorithm"),
        "passed": not blockers,
        "blockers": blockers,
    }


def verify_live_probe(
    purpose: str,
    source_bucket: str,
    destination_bucket: str,
    source_region: str,
    destination_region: str,
    destination_kms_key_arn: str,
    deployment_id: str,
    run_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    key = f"{DRILL_PREFIX}{deployment_id}/{run_id}/cross-region-{purpose}.txt"
    payload = f"lumi-node73-cross-region-object-dr:{deployment_id}:{run_id}:{purpose}\n".encode()
    expected_sha = sha256_bytes(payload)
    started = time.monotonic()
    status: str | None = None
    destination_sha: str | None = None
    destination_replication_status: str | None = None
    cleanup_source = False
    cleanup_destination = False
    blockers: list[str] = []

    with tempfile.TemporaryDirectory(prefix="lumi-object-dr-") as tmp:
        source_file = Path(tmp) / "probe.txt"
        destination_file = Path(tmp) / "replica.txt"
        source_file.write_bytes(payload)
        try:
            run_aws(
                "s3api",
                "put-object",
                "--bucket",
                source_bucket,
                "--key",
                key,
                "--body",
                str(source_file),
                "--server-side-encryption",
                "aws:kms",
                region=source_region,
            )
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() <= deadline:
                head = run_aws(
                    "s3api", "head-object", "--bucket", source_bucket, "--key", key, region=source_region
                )
                status = head.get("ReplicationStatus") if isinstance(head, dict) else None
                if status == "COMPLETED":
                    break
                if status == "FAILED":
                    blockers.append("live probe replication status became FAILED")
                    break
                time.sleep(15)
            else:
                blockers.append("live probe did not reach COMPLETED within timeout")

            elapsed = (time.monotonic() - started) / 60.0
            if status != "COMPLETED":
                blockers.append("live probe source ReplicationStatus is not COMPLETED")
            if elapsed > 15.0:
                blockers.append("live probe exceeded 15-minute replication policy")

            if status == "COMPLETED":
                destination_head = run_aws(
                    "s3api",
                    "head-object",
                    "--bucket",
                    destination_bucket,
                    "--key",
                    key,
                    region=destination_region,
                )
                destination_replication_status = destination_head.get("ReplicationStatus")
                if destination_head.get("ServerSideEncryption") != "aws:kms":
                    blockers.append("live replica is not encrypted with aws:kms")
                if normalize_kms(destination_head.get("SSEKMSKeyId")) != destination_kms_key_arn:
                    blockers.append("live replica KMS key does not match canonical DR key")
                run_aws(
                    "s3api",
                    "get-object",
                    "--bucket",
                    destination_bucket,
                    "--key",
                    key,
                    str(destination_file),
                    region=destination_region,
                )
                destination_sha = sha256_bytes(destination_file.read_bytes())
                if destination_sha != expected_sha:
                    blockers.append("live replica checksum mismatch")
                if destination_replication_status not in {"REPLICA", "COMPLETED"}:
                    blockers.append("destination object does not identify as a replica")
        finally:
            try:
                cleanup_source = delete_all_versions(source_bucket, key, source_region)
            except Exception as exc:  # cleanup evidence must remain fail-closed
                blockers.append(f"source probe cleanup failed: {type(exc).__name__}")
            try:
                cleanup_destination = delete_all_versions(destination_bucket, key, destination_region)
            except Exception as exc:
                blockers.append(f"destination probe cleanup failed: {type(exc).__name__}")

    if not cleanup_source or not cleanup_destination:
        blockers.append("live probe cleanup is incomplete")

    return {
        "purpose": purpose,
        "key_sha256": sha256_key(key),
        "source_replication_status": status,
        "destination_replication_status": destination_replication_status,
        "expected_sha256": expected_sha,
        "destination_sha256": destination_sha,
        "observed_lag_minutes": round((time.monotonic() - started) / 60.0, 3),
        "max_lag_minutes": 15,
        "source_cleanup_complete": cleanup_source,
        "destination_cleanup_complete": cleanup_destination,
        "passed": not blockers,
        "blockers": sorted(set(blockers)),
    }


def verify_current_inventory(
    purpose: str,
    source_bucket: str,
    destination_bucket: str,
    source_region: str,
    destination_region: str,
) -> dict[str, Any]:
    objects = [
        item
        for item in list_current_objects(source_bucket, source_region)
        if isinstance(item.get("Key"), str) and not item["Key"].startswith(DRILL_PREFIX)
    ]
    completed = 0
    destination_confirmed = 0
    blockers: list[str] = []
    failures: list[dict[str, str]] = []

    for item in objects:
        key = item["Key"]
        head = run_aws(
            "s3api", "head-object", "--bucket", source_bucket, "--key", key, region=source_region
        )
        status = head.get("ReplicationStatus") if isinstance(head, dict) else None
        if status == "COMPLETED":
            completed += 1
        else:
            failures.append({"key_sha256": sha256_key(key), "reason": f"source-status:{status or 'MISSING'}"})
            continue
        dest = run_aws(
            "s3api",
            "head-object",
            "--bucket",
            destination_bucket,
            "--key",
            key,
            region=destination_region,
            check=False,
        )
        if isinstance(dest, dict) and dest:
            destination_confirmed += 1
        else:
            failures.append({"key_sha256": sha256_key(key), "reason": "destination-missing"})

    total = len(objects)
    if completed != total:
        blockers.append("not every current source object has ReplicationStatus=COMPLETED")
    if destination_confirmed != total:
        blockers.append("not every current source object is readable from the DR bucket")

    return {
        "purpose": purpose,
        "current_object_count": total,
        "source_replication_completed_count": completed,
        "destination_confirmed_count": destination_confirmed,
        "coverage_percent": 100.0 if total == 0 else round(destination_confirmed * 100.0 / total, 6),
        "failure_count": len(failures),
        "failure_samples": failures[:20],
        "passed": not blockers,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify NODE-73 Production cross-region S3 recovery coverage")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-buckets", required=True, help="JSON file containing primary bucket_names")
    parser.add_argument("--destination-buckets", required=True, help="JSON file containing DR bucket names")
    parser.add_argument("--source-region", required=True)
    parser.add_argument("--destination-region", required=True)
    parser.add_argument("--destination-kms-key-arn", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--probe-timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []
    result: dict[str, Any] = {
        "schema_version": 1,
        "passed": False,
        "blockers": blockers,
    }

    try:
        manifest = load_json(Path(args.manifest))
        sources = load_json(Path(args.source_buckets))
        destinations = load_json(Path(args.destination_buckets))
        if not isinstance(manifest, dict) or manifest.get("environment") != "production":
            raise ObjectDrError("manifest must be a Production manifest")
        deployment_id = manifest.get("deployment_id")
        release_candidate = manifest.get("release_candidate")
        if not isinstance(deployment_id, str) or not deployment_id:
            raise ObjectDrError("manifest deployment_id missing")
        if not isinstance(release_candidate, dict):
            raise ObjectDrError("manifest release_candidate missing")
        if not args.run_id.isdigit():
            raise ObjectDrError("run-id must be numeric")
        if args.source_region == args.destination_region:
            raise ObjectDrError("source and destination regions must differ")
        if not isinstance(sources, dict) or not isinstance(destinations, dict):
            raise ObjectDrError("bucket maps must be JSON objects")
        if set(destinations) != set(CRITICAL_BUCKETS):
            raise ObjectDrError("DR bucket map must contain exactly assets and exports")
        if not set(CRITICAL_BUCKETS).issubset(sources):
            raise ObjectDrError("primary bucket map must contain assets and exports")
        if "sandbox" in destinations:
            raise ObjectDrError("sandbox must not be part of critical cross-region recovery")
        if args.probe_timeout_seconds <= 0 or args.probe_timeout_seconds > 900:
            raise ObjectDrError("probe timeout must be within 1..900 seconds")

        config_results: dict[str, Any] = {}
        probe_results: dict[str, Any] = {}
        inventory_results: dict[str, Any] = {}
        for purpose in CRITICAL_BUCKETS:
            source_bucket = sources[purpose]
            destination_bucket = destinations[purpose]
            if not isinstance(source_bucket, str) or not source_bucket:
                raise ObjectDrError(f"source bucket missing for {purpose}")
            if not isinstance(destination_bucket, str) or not destination_bucket:
                raise ObjectDrError(f"destination bucket missing for {purpose}")
            if source_bucket == destination_bucket:
                raise ObjectDrError(f"source and destination bucket must differ for {purpose}")

            config_results[purpose] = verify_bucket_config(
                purpose,
                source_bucket,
                destination_bucket,
                args.source_region,
                args.destination_region,
                args.destination_kms_key_arn,
            )
            if not config_results[purpose]["passed"]:
                blockers.extend(f"{purpose}: {message}" for message in config_results[purpose]["blockers"])
                continue

            probe_results[purpose] = verify_live_probe(
                purpose,
                source_bucket,
                destination_bucket,
                args.source_region,
                args.destination_region,
                args.destination_kms_key_arn,
                deployment_id,
                args.run_id,
                args.probe_timeout_seconds,
            )
            if not probe_results[purpose]["passed"]:
                blockers.extend(f"{purpose}: {message}" for message in probe_results[purpose]["blockers"])

            inventory_results[purpose] = verify_current_inventory(
                purpose,
                source_bucket,
                destination_bucket,
                args.source_region,
                args.destination_region,
            )
            if not inventory_results[purpose]["passed"]:
                blockers.extend(f"{purpose}: {message}" for message in inventory_results[purpose]["blockers"])

        result = {
            "schema_version": 1,
            "deployment_id": deployment_id,
            "release_candidate": release_candidate,
            "source_region": args.source_region,
            "destination_region": args.destination_region,
            "destination_kms_key_arn": args.destination_kms_key_arn,
            "critical_buckets": list(CRITICAL_BUCKETS),
            "configuration": config_results,
            "live_probes": probe_results,
            "current_inventory": inventory_results,
            "passed": not blockers,
            "blockers": sorted(set(blockers)),
        }
    except (OSError, json.JSONDecodeError, ObjectDrError) as exc:
        result["blockers"] = sorted(set([*result.get("blockers", []), str(exc)]))
        result["passed"] = False

    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS" if result["passed"] else "BLOCK", "output": str(output)}, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
