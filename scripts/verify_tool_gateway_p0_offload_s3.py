#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

_DEFAULT_PROBE = "reports/staging-acceptance/runtime/tool-gateway-p0-probe.json"
_DEFAULT_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-s3-evidence.json"
_INLINE_LIMIT_BYTES = 64 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BUCKET = re.compile(r"^lumi-staging-[0-9]{12}-[a-z0-9-]+-exports$")


class S3EvidenceError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise S3EvidenceError(f"unable to read Tool Gateway probe: {path}") from exc
    if not isinstance(payload, dict):
        raise S3EvidenceError("Tool Gateway probe must be a JSON object")
    return payload


def _result_ref(probe: dict[str, Any]) -> str:
    offload = probe.get("result_offload")
    if not isinstance(offload, dict):
        raise S3EvidenceError("probe result_offload is missing")
    ref = offload.get("result_ref")
    if not isinstance(ref, str) or not ref:
        raise S3EvidenceError("probe did not return a durable result_ref")
    return ref


def _parse_ref(value: str) -> tuple[str, str, str]:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise S3EvidenceError("Tool result ref is invalid") from exc
    if parsed.scheme != "s3ref" or not parsed.hostname:
        raise S3EvidenceError("Tool result ref must use s3ref://")
    bucket = parsed.hostname
    key = parsed.path.lstrip("/")
    if not _BUCKET.fullmatch(bucket):
        raise S3EvidenceError("Tool result ref is not in the staging exports bucket")
    if not key.startswith("tool-results/v1/") or ".." in key or "\x00" in key:
        raise S3EvidenceError("Tool result object key is invalid")
    fragment = parsed.fragment
    if not fragment.startswith("sha256="):
        raise S3EvidenceError("Tool result ref is missing sha256 fragment")
    digest = fragment[len("sha256=") :]
    if not _SHA256.fullmatch(digest):
        raise S3EvidenceError("Tool result ref sha256 is invalid")
    return bucket, key, digest


def _client(region: str) -> BaseClient:
    return boto3.client("s3", region_name=region)


def _public_access(client: BaseClient, bucket: str) -> dict[str, bool]:
    response = client.get_public_access_block(Bucket=bucket)
    config = response.get("PublicAccessBlockConfiguration", {})
    if not isinstance(config, dict):
        raise S3EvidenceError("S3 PublicAccessBlock configuration is missing")
    expected = {
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
    }
    actual = {key: config.get(key) is True for key in expected}
    if actual != expected:
        raise S3EvidenceError(f"S3 PublicAccessBlock is not fail-closed: {actual}")
    return actual


def _encryption(client: BaseClient, bucket: str) -> dict[str, Any]:
    response = client.get_bucket_encryption(Bucket=bucket)
    configuration = response.get("ServerSideEncryptionConfiguration", {})
    rules = configuration.get("Rules", []) if isinstance(configuration, dict) else []
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict):
        raise S3EvidenceError("S3 encryption configuration must contain one canonical rule")
    apply = rules[0].get("ApplyServerSideEncryptionByDefault", {})
    if not isinstance(apply, dict) or apply.get("SSEAlgorithm") != "aws:kms":
        raise S3EvidenceError("S3 exports bucket must use aws:kms")
    key_id = apply.get("KMSMasterKeyID")
    if not isinstance(key_id, str) or not key_id:
        raise S3EvidenceError("S3 exports bucket KMS key is missing")
    if rules[0].get("BucketKeyEnabled") is not True:
        raise S3EvidenceError("S3 exports bucket key must be enabled")
    return {
        "algorithm": "aws:kms",
        "kms_key_id": key_id,
        "bucket_key_enabled": True,
    }


def _ownership(client: BaseClient, bucket: str) -> str:
    response = client.get_bucket_ownership_controls(Bucket=bucket)
    rules = response.get("OwnershipControls", {}).get("Rules", [])
    if not isinstance(rules, list) or len(rules) != 1:
        raise S3EvidenceError("S3 ownership controls are invalid")
    ownership = rules[0].get("ObjectOwnership") if isinstance(rules[0], dict) else None
    if ownership != "BucketOwnerEnforced":
        raise S3EvidenceError("S3 exports bucket must be BucketOwnerEnforced")
    return ownership


def _not_public(client: BaseClient, bucket: str) -> bool:
    response = client.get_bucket_policy_status(Bucket=bucket)
    status = response.get("PolicyStatus", {})
    is_public = status.get("IsPublic") if isinstance(status, dict) else None
    if is_public is not False:
        raise S3EvidenceError("S3 exports bucket policy status must be non-public")
    return True


def _lifecycle(client: BaseClient, bucket: str) -> dict[str, Any]:
    response = client.get_bucket_lifecycle_configuration(Bucket=bucket)
    rules = response.get("Rules", [])
    if not isinstance(rules, list):
        raise S3EvidenceError("S3 lifecycle rules are invalid")
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("ID") != "expire-exports":
            continue
        expiration = rule.get("Expiration", {})
        days = expiration.get("Days") if isinstance(expiration, dict) else None
        if not isinstance(days, int) or days <= 0:
            raise S3EvidenceError("exports lifecycle expiration days are invalid")
        if rule.get("Status") != "Enabled":
            raise S3EvidenceError("exports lifecycle expiration must be enabled")
        return {"id": "expire-exports", "status": "Enabled", "days": days}
    raise S3EvidenceError("expire-exports lifecycle rule is missing")


def verify(probe: dict[str, Any], *, region: str) -> dict[str, Any]:
    ref = _result_ref(probe)
    bucket, key, digest = _parse_ref(ref)
    client = _client(region)
    head = client.head_object(Bucket=bucket, Key=key, ChecksumMode="ENABLED")
    length = head.get("ContentLength")
    if not isinstance(length, int) or length <= _INLINE_LIMIT_BYTES:
        raise S3EvidenceError("offloaded object does not exceed Tool Gateway inline limit")
    metadata = head.get("Metadata", {})
    if not isinstance(metadata, dict) or metadata.get("sha256") != digest:
        raise S3EvidenceError("offloaded object sha256 metadata does not match result ref")
    content_type = head.get("ContentType")
    if content_type != "application/json":
        raise S3EvidenceError("offloaded Tool Gateway result must be application/json")
    checksum = head.get("ChecksumSHA256")
    return {
        "schema_version": 1,
        "result_ref": ref,
        "bucket": bucket,
        "object_key": key,
        "sha256": digest,
        "content_length": length,
        "inline_limit_bytes": _INLINE_LIMIT_BYTES,
        "content_type": content_type,
        "checksum_sha256_b64_present": isinstance(checksum, str) and bool(checksum),
        "metadata_sha256_verified": True,
        "object_head_verified": True,
        "public_url_returned": False,
        "public_access_block": _public_access(client, bucket),
        "encryption": _encryption(client, bucket),
        "ownership": _ownership(client, bucket),
        "bucket_policy_non_public": _not_public(client, bucket),
        "lifecycle": _lifecycle(client, bucket),
    }


def main() -> int:
    probe_path = Path(os.getenv("LUMI_PROBE_INPUT", _DEFAULT_PROBE))
    output_path = Path(os.getenv("LUMI_S3_EVIDENCE_OUTPUT", _DEFAULT_OUTPUT))
    region = os.getenv("AWS_REGION", os.getenv("LUMI_AWS_REGION", ""))
    if not region or len(region) > 64 or "\x00" in region:
        raise SystemExit("AWS_REGION is required")
    try:
        payload = verify(_load(probe_path), region=region)
    except (S3EvidenceError, BotoCoreError, ClientError) as exc:
        raise SystemExit(f"Tool Gateway S3 offload evidence failed: {exc}") from exc
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
