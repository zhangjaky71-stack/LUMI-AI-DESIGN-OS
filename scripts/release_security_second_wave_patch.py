#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match in {path}, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Keep the Python audit frozen while omitting only local workspace packages that
# pip-audit cannot hash/install as editable directories. All third-party locked
# dependencies emitted by those workspace packages remain in the export.
replace_once(
    ".github/workflows/security-release-gate.yml",
    "uv export --all-packages --frozen --no-dev --format requirements-txt > /tmp/requirements.txt",
    "uv export --all-packages --frozen --no-dev --no-emit-workspace --format requirements-txt > /tmp/requirements.txt",
)
replace_once(
    ".github/workflows/security-release-gate.yml",
    "          ignore-unfixed: false\n",
    "          ignore-unfixed: false\n          trivyignores: .trivyignore.yaml\n",
)

# Replace unrestricted S3 provisioning with the explicit bucket-control actions
# used by the storage and cross-region object-DR Terraform resources.
s3_actions = """      \"s3:CreateBucket\",
      \"s3:DeleteBucket\",
      \"s3:GetBucketAcl\",
      \"s3:GetBucketLocation\",
      \"s3:GetBucketTagging\",
      \"s3:PutBucketTagging\",
      \"s3:DeleteBucketTagging\",
      \"s3:TagResource\",
      \"s3:UntagResource\",
      \"s3:ListTagsForResource\",
      \"s3:GetBucketOwnershipControls\",
      \"s3:PutBucketOwnershipControls\",
      \"s3:GetBucketPublicAccessBlock\",
      \"s3:PutBucketPublicAccessBlock\",
      \"s3:DeleteBucketPublicAccessBlock\",
      \"s3:GetBucketVersioning\",
      \"s3:PutBucketVersioning\",
      \"s3:GetEncryptionConfiguration\",
      \"s3:PutEncryptionConfiguration\",
      \"s3:DeleteBucketEncryption\",
      \"s3:GetLifecycleConfiguration\",
      \"s3:PutLifecycleConfiguration\",
      \"s3:DeleteBucketLifecycle\",
      \"s3:GetBucketPolicy\",
      \"s3:PutBucketPolicy\",
      \"s3:DeleteBucketPolicy\",
      \"s3:GetReplicationConfiguration\",
      \"s3:PutReplicationConfiguration\",
      \"s3:ListBucket\",
      \"s3:ListBucketVersions\","""
replace_once(
    "infra/iac/bootstrap/main.tf",
    '      "s3:*",',
    s3_actions,
)

# Public provider/webhook egress is isolated in its own SG. Narrow transport to
# HTTPS only and document the exact intentional public-destination exception.
replace_once(
    "infra/iac/modules/network/main.tf",
    'resource "aws_security_group" "app_internet_egress" {',
    '# Public provider/webhook egress is intentionally isolated from the base app identity SG.\n'
    '# Only TLS/443 is permitted, and this SG is never attached to sandbox-runtime or outbox-dispatcher.\n'
    '#trivy:ignore:AVD-AWS-0104\n'
    'resource "aws_security_group" "app_internet_egress" {',
)
replace_once(
    "infra/iac/modules/network/main.tf",
    '  egress {\n    protocol    = "-1"\n    from_port   = 0\n    to_port     = 0\n    cidr_blocks = ["0.0.0.0/0"]\n  }',
    '  egress {\n    protocol    = "tcp"\n    from_port   = 443\n    to_port     = 443\n    cidr_blocks = ["0.0.0.0/0"]\n  }',
)

# The ALB is deliberately the public HTTPS ingress boundary; downstream ECS
# tasks remain private and the listener requires a certificate/TLS policy.
replace_once(
    "infra/iac/modules/compute/main.tf",
    'resource "aws_lb" "this" {',
    '# Public HTTPS ingress is intentional; ECS tasks remain private behind this ALB.\n'
    '# The listener is certificate-backed and restricted to the pinned TLS policy below.\n'
    '#trivy:ignore:AVD-AWS-0053\n'
    'resource "aws_lb" "this" {',
)

ignore_path = ROOT / ".trivyignore.yaml"
if ignore_path.exists():
    raise SystemExit("refusing to overwrite an existing .trivyignore.yaml")
ignore_path.write_text(
    """misconfigurations:
  - id: AVD-DS-0002
    paths:
      - infra/docker/postgres-recovery/Dockerfile
    statement: >-
      The recovery image starts as root only to create, chown, and chmod the WAL archive directory.
      Its wrapper then execs the upstream PostgreSQL docker-entrypoint, which owns the runtime
      privilege drop to the postgres user; this exception is limited to this recovery Dockerfile.
""",
    encoding="utf-8",
)

# Turn the intentional egress/ALB boundaries and S3 least-privilege change into
# durable production-IaC contract assertions.
replace_once(
    "scripts/validate_production_iac_contract.py",
    '    require(\'cidr_blocks = ["0.0.0.0/0"]\' in internet_sg, "explicit app Internet egress SG missing")\n',
    '    require(\'cidr_blocks = ["0.0.0.0/0"]\' in internet_sg, "explicit app Internet egress SG missing")\n'
    '    require_hcl_assignment(internet_sg, "protocol", \'"tcp"\', "app Internet egress must be TCP-only")\n'
    '    require_hcl_assignment(internet_sg, "from_port", "443", "app Internet egress must start at HTTPS/443")\n'
    '    require_hcl_assignment(internet_sg, "to_port", "443", "app Internet egress must end at HTTPS/443")\n'
    '    require("#trivy:ignore:AVD-AWS-0104" in network, "public HTTPS egress exception must be resource-scoped")\n'
    '    require("#trivy:ignore:AVD-AWS-0053" in compute, "public ALB exception must be resource-scoped")\n'
    '    require(\'"s3:*"\' not in bootstrap, "bootstrap platform provisioner must not grant unrestricted S3 actions")\n'
    '    for s3_action in (\n'
    '        "s3:CreateBucket",\n'
    '        "s3:PutBucketOwnershipControls",\n'
    '        "s3:PutBucketPublicAccessBlock",\n'
    '        "s3:PutBucketVersioning",\n'
    '        "s3:PutEncryptionConfiguration",\n'
    '        "s3:PutLifecycleConfiguration",\n'
    '        "s3:PutBucketPolicy",\n'
    '        "s3:PutReplicationConfiguration",\n'
    '    ):\n'
    '        require(f\'"{s3_action}"\' in bootstrap, f"bootstrap platform provisioner missing {s3_action}")\n',
)

# Bind the recovery-root exception to a verified privilege-boundary contract.
replace_once(
    "scripts/validate_recovery_contract.py",
    "\ndef validate_fail_closed_planner() -> None:\n",
    """
def validate_postgres_recovery_privilege_boundary() -> None:
    dockerfile = (ROOT / "infra/docker/postgres-recovery/Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "infra/docker/postgres-recovery/primary-entrypoint.sh").read_text(encoding="utf-8")
    require("USER root" in dockerfile, "recovery image bootstrap user contract missing")
    require(
        'ENTRYPOINT ["lumi-postgres-primary-entrypoint"]' in dockerfile,
        "recovery image must execute the audited wrapper",
    )
    require(
        'chown postgres:postgres "$archive_dir"' in entrypoint,
        "recovery bootstrap must hand archive ownership to postgres",
    )
    require(
        'exec /usr/local/bin/docker-entrypoint.sh "$@"' in entrypoint,
        "recovery wrapper must delegate to the upstream PostgreSQL entrypoint for runtime privilege drop",
    )


def validate_fail_closed_planner() -> None:
""",
)
replace_once(
    "scripts/validate_recovery_contract.py",
    "    validate_files()\n    validate_fail_closed_planner()\n",
    "    validate_files()\n    validate_postgres_recovery_privilege_boundary()\n    validate_fail_closed_planner()\n",
)

print("security second-wave patch: applied")
