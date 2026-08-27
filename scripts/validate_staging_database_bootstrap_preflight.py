#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPORT = Path("reports/staging-database-identity/runtime/environment-preflight.json")
ALLOWED = {
    "plan-database-bootstrap",
    "apply-database-bootstrap",
    "run-database-bootstrap",
}
REQUIRED = {
    "AWS_REGION",
    "AWS_DEPLOY_ROLE_ARN",
    "TF_STATE_BUCKET",
    "TF_VAR_account_id",
    "TF_VAR_core_state_bucket",
}


def value(name: str) -> str:
    return os.environ.get(name, "").strip()


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    operation = value("OPERATION")
    missing = sorted(name for name in REQUIRED if not value(name))
    invalid: dict[str, str] = {}

    if operation not in ALLOWED:
        invalid["OPERATION"] = f"unsupported database bootstrap operation: {operation!r}"

    region = value("AWS_REGION")
    account = value("TF_VAR_account_id")
    role = value("AWS_DEPLOY_ROLE_ARN")
    bucket = value("TF_STATE_BUCKET")
    core_bucket = value("TF_VAR_core_state_bucket")

    if region and not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+", region):
        invalid["AWS_REGION"] = "must be an AWS region identifier"
    if account and not re.fullmatch(r"[0-9]{12}", account):
        invalid["TF_VAR_account_id"] = "must be a 12-digit AWS account id"
    if role:
        match = re.fullmatch(r"arn:aws(?:-[a-z]+)?:iam::([0-9]{12}):role/(.+)", role)
        if match is None:
            invalid["AWS_DEPLOY_ROLE_ARN"] = "must be an IAM role ARN"
        elif account and match.group(1) != account:
            invalid["AWS_DEPLOY_ROLE_ARN"] = "role account must match TF_VAR_account_id"
        elif match.group(2) != "lumi-staging-github-deploy":
            invalid["AWS_DEPLOY_ROLE_ARN"] = "must target lumi-staging-github-deploy"
    if bucket and not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        invalid["TF_STATE_BUCKET"] = "must be a valid lowercase S3 bucket name"
    if core_bucket and bucket and core_bucket != bucket:
        invalid["TF_VAR_core_state_bucket"] = "must equal TF_STATE_BUCKET"

    payload = {
        "schema_version": 1,
        "kind": "LUMI_STAGING_DATABASE_IDENTITY_PREFLIGHT_V1",
        "status": "PASS" if not missing and not invalid else "FAIL",
        "operation": operation or None,
        "required_keys": sorted(REQUIRED),
        "missing_keys": missing,
        "invalid_keys": invalid,
        "secret_values_recorded": False,
    }
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 64


if __name__ == "__main__":
    raise SystemExit(main())
