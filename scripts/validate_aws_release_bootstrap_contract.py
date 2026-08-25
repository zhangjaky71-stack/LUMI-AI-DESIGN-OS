#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/aws_release_bootstrap_cloudshell.sh"
BOOTSTRAP_MAIN = ROOT / "infra/iac/bootstrap/main.tf"
BOOTSTRAP_VARIABLES = ROOT / "infra/iac/bootstrap/variables.tf"

EXPECTED_BOOTSTRAP_REF = "070315c2d3dd697bc87bc3a70acd7a3338175e40"
EXPECTED_TERRAFORM_VERSION = "1.14.6"
EXPECTED_TERRAFORM_SHA256 = {
    "linux_amd64": "364c6ee08b0cb8fcbb28a115aacb2aa48e88abc56c149170bd65c2f75d98ea8d",
    "linux_arm64": "190037f64695556ac75965c00da5d85b3663f38553d909e9a51c4490cba4b6c1",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"AWS release bootstrap contract invalid: {message}")


def main() -> int:
    require(SCRIPT.is_file(), "missing CloudShell bootstrap script")
    require(BOOTSTRAP_MAIN.is_file(), "missing bootstrap main.tf")
    require(BOOTSTRAP_VARIABLES.is_file(), "missing bootstrap variables.tf")

    script = SCRIPT.read_text(encoding="utf-8")
    main_tf = BOOTSTRAP_MAIN.read_text(encoding="utf-8")
    variables_tf = BOOTSTRAP_VARIABLES.read_text(encoding="utf-8")

    require(
        f'BOOTSTRAP_REF="${{LUMI_BOOTSTRAP_REF:-{EXPECTED_BOOTSTRAP_REF}}}"' in script,
        "CloudShell bootstrap source SHA is not pinned to the hosted-validated bootstrap",
    )
    require(
        f'TERRAFORM_VERSION="{EXPECTED_TERRAFORM_VERSION}"' in script,
        "Terraform CLI version is not exactly pinned",
    )
    for arch, checksum in EXPECTED_TERRAFORM_SHA256.items():
        require(checksum in script, f"missing pinned Terraform SHA-256 for {arch}")
    require("sha256sum --check --status" in script, "Terraform archive checksum is not enforced")
    require("https://releases.hashicorp.com/terraform/" in script, "Terraform download is not bound to HashiCorp releases")

    require("aws sts get-caller-identity" in script, "AWS caller identity preflight is missing")
    require("aws ec2 describe-regions" in script, "AWS Region preflight is missing")
    require(
        'git -C "$WORKDIR" checkout -q --detach FETCH_HEAD' in script,
        "bootstrap source checkout is not detached",
    )
    require(
        '[[ "$(git -C "$WORKDIR" rev-parse HEAD)" == "$BOOTSTRAP_REF" ]]' in script,
        "bootstrap source SHA equality check is missing",
    )

    require("terraform -chdir=\"$ROOT\" plan" in script, "bootstrap Terraform plan is missing")
    require("terraform -chdir=\"$ROOT\" show -json tfplan" in script, "machine-readable plan inspection is missing")
    require("if 'delete' in actions:" in script, "delete/replace plan rejection is missing")
    require("bootstrap plan contains delete/replace actions" in script, "delete/replace plan failure is not explicit")
    require('APPLY_TOKEN="APPLY_AWS_BOOTSTRAP"' in script, "explicit bootstrap apply token is missing")
    require(
        '"${LUMI_BOOTSTRAP_APPLY:-}" != "$APPLY_TOKEN"' in script,
        "bootstrap apply is not gated by explicit acknowledgement",
    )
    require("terraform -chdir=\"$ROOT\" apply -input=false tfplan" in script, "apply does not consume the reviewed plan")

    require('STATE_KEY="lumi/bootstrap/terraform.tfstate"' in script, "bootstrap state key is not fixed")
    require("--sse aws:kms" in script, "bootstrap state upload does not require KMS encryption")
    require("--sse-kms-key-id" in script, "bootstrap state upload is not bound to the created KMS key")
    require("head-object" in script and "head-bucket" in script, "bootstrap rerun state guards are missing")
    require("refusing an unaudited import/overwrite" in script, "foreign/pre-existing state bucket fail-closed guard is missing")

    for marker in (
        "aws rds describe-db-engine-versions",
        "aws elasticache describe-cache-engine-versions",
        "aws mq describe-broker-engine-types",
        "aws mq describe-broker-instance-options",
    ):
        require(marker in script, f"real Region capability query missing: {marker}")
    require("lumi-aws-bootstrap-handoff.json" in script, "bootstrap handoff artifact is missing")
    require("LUMI_AWS_RELEASE_BOOTSTRAP_HANDOFF_V1" in script, "bootstrap handoff schema is missing")
    require("No Staging/Production application resources were deployed" in script, "bootstrap scope declaration is missing")

    forbidden_script_markers = (
        "git push",
        "gh api",
        "gh variable",
        "gh secret",
        "aws s3 rm",
        "aws s3api delete-",
        "aws iam delete-",
        "aws kms schedule-key-deletion",
    )
    for marker in forbidden_script_markers:
        require(marker not in script, f"forbidden bootstrap side effect detected: {marker}")

    require(
        'resource "aws_iam_openid_connect_provider" "github"' in main_tf,
        "bootstrap cannot create the GitHub Actions OIDC provider",
    )
    require("token.actions.githubusercontent.com" in main_tf, "GitHub OIDC provider URL/trust is missing")
    require("sts.amazonaws.com" in main_tf, "GitHub OIDC audience is missing")
    require("environment:staging" in main_tf and "environment:production" in main_tf, "environment-scoped OIDC subjects are missing")
    require("enable_key_rotation     = true" in main_tf, "Terraform-state KMS key rotation is not enabled")
    require("BucketOwnerEnforced" in main_tf, "Terraform-state bucket ownership enforcement is missing")
    require("block_public_acls       = true" in main_tf, "Terraform-state public ACL block is missing")
    require("restrict_public_buckets = true" in main_tf, "Terraform-state public bucket restriction is missing")
    require('status = "Enabled"' in main_tf, "Terraform-state versioning is not enabled")
    require('sse_algorithm     = "aws:kms"' in main_tf, "Terraform-state bucket does not require KMS encryption")
    require("aws:SecureTransport" in main_tf, "Terraform-state TLS-only bucket policy is missing")

    require('default     = null' in variables_tf, "optional bootstrap inputs are not nullable/defaulted")
    require(
        re.search(r'variable "github_oidc_provider_arn"[\s\S]+?default\s*=\s*null', variables_tf) is not None,
        "existing GitHub OIDC provider reuse is not optional",
    )
    require(
        re.search(r'variable "state_bucket_name"[\s\S]+?default\s*=\s*null', variables_tf) is not None,
        "state bucket name is not auto-derivable",
    )

    print("AWS release bootstrap contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
