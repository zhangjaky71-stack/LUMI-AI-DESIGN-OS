#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IAC = ROOT / "infra" / "iac-alicloud"


def read(relative: str) -> str:
    path = IAC / relative
    if not path.is_file():
        raise SystemExit(f"Alibaba Cloud IaC contract invalid: missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def read_root(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit(f"Alibaba Cloud IaC contract invalid: missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Alibaba Cloud IaC contract invalid: {message}")


def main() -> int:
    bootstrap = read("bootstrap/main.tf")
    bootstrap_identity = read("bootstrap/github_oidc.tf")
    bootstrap_variables = read("bootstrap/variables.tf")
    bootstrap_outputs = read("bootstrap/outputs.tf")
    bootstrap_versions = read("bootstrap/versions.tf")
    core_versions = read("core/versions.tf")
    core_variables = read("core/variables.tf")
    locals_tf = read("core/locals.tf")
    network = read("core/network.tf")
    storage = read("core/storage.tf")
    data = read("core/data.tf")
    ack = read("core/ack.tf")
    registry = read("core/registry.tf")
    messaging = read("core/messaging.tf")
    backend = read("core/backend.hcl.example")
    kustomization = read("k8s/base/kustomization.yaml")
    runtime_config = read("k8s/base/configmap.yaml")
    rbac = read("k8s/base/rbac.yaml")
    network_policies = read("k8s/base/network-policies.yaml")
    workloads = read("k8s/base/workloads.yaml")
    services = read("k8s/base/services.yaml")
    ingress = read("k8s/base/ingress.yaml")
    migration = read("k8s/migration/migration-job.yaml")
    migration_kustomization = read("k8s/migration/kustomization.yaml")
    s3_store = read_root("services/asset-storage/src/lumi_asset_storage/s3.py")
    ack_backend = read_root(
        "services/sandbox-runtime/src/lumi_sandbox_runtime/ack_backend.py"
    )
    hosted_service = read_root(
        "services/sandbox-runtime/src/lumi_sandbox_runtime/hosted_service.py"
    )
    child_cli = read_root("services/sandbox-runtime/src/lumi_sandbox_runtime/child_cli.py")
    image_workflow = read_root(".github/workflows/build-alicloud-runtime-images.yml")

    terraform_sources = "\n".join(path.read_text(encoding="utf-8") for path in IAC.rglob("*.tf"))
    require('resource "aws_' not in terraform_sources, "AWS resources leaked into the Alibaba Cloud root")
    require('source  = "aliyun/alicloud"' in bootstrap_versions, "Alibaba Cloud provider source is not pinned")
    require('version = "1.291.0"' in bootstrap_versions, "bootstrap provider version drifted")
    require('version = "1.291.0"' in core_versions, "core provider version drifted")
    require('backend "oss" {}' in core_versions, "core must use the protected OSS backend")
    require('source  = "hashicorp/random"' in core_versions, "credential generator provider is missing")
    require('version = "3.9.0"' in core_versions, "random provider version drifted")

    for marker in (
        'resource "alicloud_cs_managed_kubernetes" "runtime"',
        'cluster_spec                 = "ack.pro.small"',
        "slb_internet_enabled         = false",
        "enable_rrsa                  = true",
        "is_enterprise_security_group = true",
        "auto_mode {",
        'name = "terway-eniip"',
        'name = "alb-ingress-controller"',
        'name = "managed-aliyun-acr-credential-helper"',
        'name = "loongcollector"',
        'name = "metrics-server"',
        'name = "managed-coredns"',
        'name = "arms-prometheus"',
    ):
        require(marker in ack, f"ACK Auto Mode contract missing: {marker}")
    require(
        "alicloud_cs_serverless_kubernetes" not in terraform_sources,
        "deprecated ACK Serverless resource must not be used",
    )

    for marker in (
        'default     = "cn-hangzhou"',
        '"cn-hangzhou-h"',
        '"cn-hangzhou-i"',
        '"cn-hangzhou-j"',
    ):
        require(marker in bootstrap_variables, f"bootstrap region/zone marker missing: {marker}")
        require(marker in core_variables, f"core region/zone marker missing: {marker}")

    for marker in (
        'resource "alicloud_oss_bucket" "terraform_state"',
        'resource "alicloud_oss_bucket_public_access_block" "terraform_state"',
        'block_public_access = true',
        'sse_algorithm = "AES256"',
        'status = "Enabled"',
        'resource "alicloud_ots_instance" "terraform_lock"',
        'resource "alicloud_ots_table" "terraform_lock"',
        'name = "LockID"',
        'ignore_changes = [versioning, server_side_encryption_rule]',
    ):
        require(marker in bootstrap, f"bootstrap protection missing: {marker}")

    for marker in (
        'resource "alicloud_ims_oidc_provider" "github_actions"',
        'issuer_url         = "https://token.actions.githubusercontent.com"',
        'client_ids         = ["sts.aliyuncs.com"]',
        'fingerprints = ["CABD2A79A1076A31F21D253635CB039D4329A5E8"]',
        'resource "alicloud_ram_role" "github_acr_push"',
        '"oidc:iss" = "https://token.actions.githubusercontent.com"',
        '"oidc:aud" = "sts.aliyuncs.com"',
        '"oidc:sub" = local.github_oidc_subject',
        'resource "alicloud_ram_policy" "github_acr_push"',
        '"cr:GetAuthorizationToken"',
        '"cr:PullRepository"',
        '"cr:PushRepository"',
        'repository/${var.acr_namespace}/*',
        'resource "alicloud_ram_role_policy_attachment" "github_acr_push"',
    ):
        require(marker in bootstrap_identity, f"GitHub OIDC bootstrap contract missing: {marker}")
    require(
        'default     = "refs/heads/codex/alicloud-deployment"' in bootstrap_variables,
        "GitHub OIDC trust must target the exact deployment branch",
    )
    for marker in (
        'output "github_oidc_provider_arn"',
        'output "github_acr_role_arn"',
        'output "github_acr_repository_boundary"',
    ):
        require(marker in bootstrap_outputs, f"GitHub OIDC bootstrap output missing: {marker}")
    for marker in (
        "id-token: write",
        "crpi-5765pzu53bg0a9z6.cn-hangzhou.personal.cr.aliyuncs.com",
        "aliyun/configure-aliyun-credentials-action@1e5248c8d5d93a8781ac344a68e19a43341e79e6",
        "aliyun/setup-aliyun-cli-action@09a5f86915bb556e27bf050e9a5e339aeb073df5",
        "version: 3.4.11",
        "cr GET /tokens",
        "--version 2016-06-07",
        "::add-mask::$acr_username",
        "docker login \"$ACR_REGISTRY\"",
    ):
        require(marker in image_workflow, f"Alibaba Cloud image OIDC workflow missing: {marker}")
    for forbidden in (
        "ALICLOUD_ACR_USERNAME",
        "ALICLOUD_ACR_PASSWORD",
        "secrets.ALICLOUD",
    ):
        require(forbidden not in image_workflow, f"long-lived ACR credential reference remains: {forbidden}")

    for cidr in (
        '"10.42.0.0/16"',
        '"10.42.0.0/24"',
        '"10.42.16.0/20"',
        '"10.42.80.0/24"',
    ):
        require(cidr in network + locals_tf, f"network boundary missing: {cidr}")
    for resource in (
        "alicloud_vpc",
        "alicloud_vswitch",
        "alicloud_nat_gateway",
        "alicloud_eip_address",
        "alicloud_snat_entry",
        "alicloud_security_group",
    ):
        require(f'resource "{resource}"' in network, f"core network resource missing: {resource}")

    require('for_each = local.bucket_names' in storage, "three declared application buckets must share protections")
    require('acl    = "private"' in storage, "application OSS buckets must be private")
    require('block_public_access = true' in storage, "application OSS public access block missing")
    require('sse_algorithm = "AES256"' in storage, "application OSS encryption missing")
    require(
        'ignore_changes = [versioning, server_side_encryption_rule]' in storage,
        "application OSS bucket must ignore provider inline protection mirrors",
    )

    for marker in (
        'engine                   = "PostgreSQL"',
        'engine_version           = "15.0"',
        'instance_type            = "pg.n1e.1c.1m"',
        'db_instance_storage_type = "cloud_essd"',
        'instance_class      = "redis.amber.master.small.multithread"',
        'ssl_enable          = "Enable"',
        'resource "random_password" "db_account"',
        'resource "random_password" "db_migration"',
        'resource "random_password" "redis"',
        'account_name        = "lumi_migration"',
        'privilege    = "ReadWrite"',
        'privilege    = "DBOwner"',
    ):
        require(marker in data, f"data-service contract missing: {marker}")

    for runtime in (
        "api",
        "agent-runtime",
        "model-gateway",
        "tool-gateway",
        "worker-media",
        "sandbox-runtime",
    ):
        require(f'"{runtime}"' in locals_tf, f"runtime repository boundary missing: {runtime}")
    require('repo_type = "PRIVATE"' in registry, "ACR repositories must be private")

    for name in (
        "lumi.jobs",
        "lumi.domain",
        "lumi.dlx",
        "lumi.media.image",
        "lumi.media.video",
        "lumi.media.export",
        "lumi.asset.processing",
    ):
        require(name in messaging, f"RabbitMQ topology marker missing: {name}")
    require('default     = false' in core_variables, "RabbitMQ must remain opt-in until billing approval")

    for marker in (
        'bucket              = "lumi-terraform-state-1153410507483251-cn-hangzhou"',
        'tablestore_table    = "terraform_lock"',
    ):
        require(marker in backend, f"remote backend example missing: {marker}")

    for marker in (
        'signature_version: str = "s3v4"',
        '{"s3", "s3v4"}',
        '"addressing_style": "path" if force_path_style else "virtual"',
        "aws_session_token=session_token",
    ):
        require(marker in s3_store, f"OSS-compatible S3 client marker missing: {marker}")
    for marker in (
        'backend == "ack"',
        "ACKRemoteSandboxBackend.from_env()",
    ):
        require(marker in hosted_service, f"ACK backend selection marker missing: {marker}")
    for marker in (
        "class ACKRemoteSandboxBackend",
        "LUMI_SANDBOX_CHILD_IMAGE",
        "SANDBOX_ACK_CHILD_IMAGE_DIGEST_REQUIRED",
        '"backoffLimit": 0',
        '"ttlSecondsAfterFinished"',
        '"automountServiceAccountToken": False',
        '"readOnlyRootFilesystem": True',
        '"k8s.aliyun.com/eci-security-group"',
    ):
        require(marker in ack_backend, f"ACK sandbox isolation marker missing: {marker}")
    require(
        'signature = os.getenv("LUMI_S3_SIGNATURE_VERSION", "s3v4")' in child_cli,
        "sandbox child must honor the OSS signature version",
    )

    for runtime in (
        "api",
        "agent-runtime",
        "model-gateway",
        "tool-gateway",
        "worker-media",
        "sandbox-runtime",
        "outbox-dispatcher",
    ):
        require(f"name: {runtime}" in workloads, f"ACK workload missing: {runtime}")
    require(
        workloads.count("kind: Deployment") == 7,
        "ACK base must declare exactly seven persistent Deployments",
    )
    require(
        workloads.count("readinessProbe:") == 7
        and workloads.count("livenessProbe:") == 7,
        "every persistent workload needs readiness and liveness probes",
    )
    for runtime in ("api", "agent-runtime", "model-gateway", "tool-gateway", "sandbox-runtime"):
        require(f"name: {runtime}" in services, f"private ClusterIP service missing: {runtime}")
    require(services.count("type: ClusterIP") == 5, "only HTTP runtimes need ClusterIP services")
    require("ingressClassName: alb" in ingress, "ACK API ingress must use ALB")
    require(
        "alb.ingress.kubernetes.io/certificate-id" in ingress,
        "ACK API ingress must be certificate backed",
    )
    require(
        "name: lumi-sandbox-job-controller" in rbac
        and 'verbs: ["create", "get", "delete"]' in rbac,
        "sandbox controller RBAC must remain Job-only",
    )
    require("name: default-deny" in network_policies, "default-deny NetworkPolicy missing")
    require(
        "LUMI_S3_ENDPOINT_URL: https://s3.oss-cn-hangzhou-internal.aliyuncs.com"
        in runtime_config,
        "ACK runtimes must use the internal OSS S3 endpoint",
    )
    require("LUMI_S3_SIGNATURE_VERSION: s3" in runtime_config, "OSS Signature V2 missing")
    require(
        "LUMI_SANDBOX_REMOTE_BACKEND: ack" in runtime_config,
        "sandbox runtime must select ACK explicitly",
    )
    require(
        kustomization.count("digest: sha256:REPLACE_WITH_") == 6,
        "six runtime images must be replaced with immutable digests",
    )
    require(
        "secrets.example.yaml" not in kustomization,
        "secret example must never be part of the applied base",
    )
    require(
        'command: ["alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"]'
        in migration,
        "one-shot Alembic upgrade Job is missing",
    )
    require("backoffLimit: 0" in migration, "migration Job must fail closed")
    require(
        "digest: sha256:REPLACE_WITH_API_DIGEST" in migration_kustomization,
        "migration image must be digest pinned",
    )

    print("Alibaba Cloud IaC contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
