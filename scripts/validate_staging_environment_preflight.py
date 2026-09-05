#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPORT = Path("reports/staging-operations/runtime/environment-preflight.json")

COMMON_KEYS = {
    "AWS_REGION",
    "AWS_DEPLOY_ROLE_ARN",
    "TF_STATE_BUCKET",
    "TF_VAR_account_id",
}
CORE_KEYS = {
    "TF_VAR_availability_zones",
    "TF_VAR_postgres_engine_version",
    "TF_VAR_redis_engine_version",
    "TF_VAR_rabbitmq_engine_version",
    "TF_VAR_rabbitmq_instance_type",
}
MIGRATION_KEYS = {"TF_VAR_core_state_bucket"}
APP_KEYS = {
    "TF_VAR_core_state_bucket",
    "TF_VAR_certificate_arn",
    "TF_VAR_domain_name",
    "TF_VAR_hosted_zone_id",
}


def value(name: str) -> str:
    return os.environ.get(name, "").strip()


def invalid_placeholder(raw: str) -> bool:
    upper = raw.upper()
    return not raw or "REPLACE" in upper or "PLACEHOLDER" in upper or "TODO" in upper


def required_keys(operation: str) -> set[str]:
    keys = set(COMMON_KEYS)
    if operation in {"plan-core", "apply-core"}:
        keys |= CORE_KEYS
    elif operation in {"plan-migration", "apply-migration", "run-migration"}:
        keys |= MIGRATION_KEYS
    elif operation in {"plan-app", "apply-app"}:
        keys |= APP_KEYS
    elif operation == "promote-runtime-images":
        pass
    else:
        raise ValueError(f"unsupported Staging operation: {operation!r}")
    return keys


def validate(operation: str, keys: set[str]) -> tuple[list[str], dict[str, str]]:
    missing = sorted(name for name in keys if not value(name))
    invalid: dict[str, str] = {}

    region = value("AWS_REGION")
    account = value("TF_VAR_account_id")
    role = value("AWS_DEPLOY_ROLE_ARN")
    bucket = value("TF_STATE_BUCKET")

    if region and not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+", region):
        invalid["AWS_REGION"] = "must be an AWS region identifier"
    if account and not re.fullmatch(r"[0-9]{12}", account):
        invalid["TF_VAR_account_id"] = "must be a 12-digit AWS account id"
    if role:
        role_match = re.fullmatch(r"arn:aws(?:-[a-z]+)?:iam::([0-9]{12}):role/(.+)", role)
        if role_match is None:
            invalid["AWS_DEPLOY_ROLE_ARN"] = "must be an IAM role ARN"
        elif account and role_match.group(1) != account:
            invalid["AWS_DEPLOY_ROLE_ARN"] = "role account must match TF_VAR_account_id"
        elif role_match.group(2) != "lumi-staging-github-deploy":
            invalid["AWS_DEPLOY_ROLE_ARN"] = "must target lumi-staging-github-deploy"
    if bucket and not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        invalid["TF_STATE_BUCKET"] = "must be a valid lowercase S3 bucket name"

    if "TF_VAR_core_state_bucket" in keys:
        core_bucket = value("TF_VAR_core_state_bucket")
        if core_bucket and bucket and core_bucket != bucket:
            invalid["TF_VAR_core_state_bucket"] = "must equal TF_STATE_BUCKET"

    if "TF_VAR_availability_zones" in keys:
        raw = value("TF_VAR_availability_zones")
        if raw:
            try:
                zones = json.loads(raw)
            except json.JSONDecodeError:
                invalid["TF_VAR_availability_zones"] = "must be a JSON list"
            else:
                if (
                    not isinstance(zones, list)
                    or len(zones) != 3
                    or len(set(zones)) != 3
                    or not all(isinstance(zone, str) and zone for zone in zones)
                ):
                    invalid["TF_VAR_availability_zones"] = "must contain exactly three distinct AZ names"
                elif region and not all(zone.startswith(region) for zone in zones):
                    invalid["TF_VAR_availability_zones"] = "all AZs must belong to AWS_REGION"

    for name in (
        "TF_VAR_postgres_engine_version",
        "TF_VAR_redis_engine_version",
        "TF_VAR_rabbitmq_engine_version",
        "TF_VAR_rabbitmq_instance_type",
    ):
        if name in keys and value(name) and invalid_placeholder(value(name)):
            invalid[name] = "must be a real Region-validated value, not a placeholder"

    if operation in {"plan-app", "apply-app"}:
        certificate = value("TF_VAR_certificate_arn")
        domain = value("TF_VAR_domain_name")
        zone = value("TF_VAR_hosted_zone_id")
        profile = value("VIDEO_MODEL_PROFILE_INPUT") or value("VIDEO_MODEL_PROFILE_DEFAULT")
        if certificate and not re.fullmatch(
            r"arn:aws(?:-[a-z]+)?:acm:[a-z0-9-]+:[0-9]{12}:certificate/[0-9a-fA-F-]+",
            certificate,
        ):
            invalid["TF_VAR_certificate_arn"] = "must be an ACM certificate ARN"
        if domain and (
            len(domain) > 253
            or not re.fullmatch(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", domain)
        ):
            invalid["TF_VAR_domain_name"] = "must be a valid FQDN"
        if zone and not re.fullmatch(r"Z[A-Z0-9]+", zone):
            invalid["TF_VAR_hosted_zone_id"] = "must be a Route53 hosted zone id"
        if not profile:
            missing.append("VIDEO_MODEL_PROFILE_INPUT|VIDEO_MODEL_PROFILE_DEFAULT")
        elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}", profile) or invalid_placeholder(profile):
            invalid["VIDEO_MODEL_PROFILE"] = "must be a real logical Model Gateway profile"

    return sorted(set(missing)), invalid


def main() -> int:
    operation = value("OPERATION")
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    try:
        keys = required_keys(operation)
        missing, invalid = validate(operation, keys)
    except ValueError as exc:
        payload = {
            "schema_version": 1,
            "kind": "LUMI_STAGING_ENVIRONMENT_PREFLIGHT_V1",
            "status": "FAIL",
            "operation": operation or None,
            "required_keys": [],
            "missing_keys": [],
            "invalid_keys": {"OPERATION": str(exc)},
            "secret_values_recorded": False,
        }
        REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, sort_keys=True))
        return 64

    payload = {
        "schema_version": 1,
        "kind": "LUMI_STAGING_ENVIRONMENT_PREFLIGHT_V1",
        "status": "PASS" if not missing and not invalid else "FAIL",
        "operation": operation,
        "required_keys": sorted(keys),
        "missing_keys": missing,
        "invalid_keys": invalid,
        "secret_values_recorded": False,
    }
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 64


if __name__ == "__main__":
    raise SystemExit(main())
