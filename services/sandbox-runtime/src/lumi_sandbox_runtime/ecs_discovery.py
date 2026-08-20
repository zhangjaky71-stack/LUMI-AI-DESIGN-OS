from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .ecs_backend import ECSRemoteSandboxBackend

_TASK_ARN = re.compile(r"^arn:aws[a-z-]*:ecs:[^:]+:(\d{12}):task/(?:[^/]+/)?[^/]+$")


class ECSDiscoveryError(RuntimeError):
    pass


def discover_remote_backend() -> ECSRemoteSandboxBackend:
    region = _required_env("AWS_REGION", fallback="AWS_DEFAULT_REGION", max_length=64)
    environment = _required_env("LUMI_ENV", fallback="LUMI_ENVIRONMENT", max_length=64)
    metadata = _task_metadata()
    task_arn = metadata.get("TaskARN")
    cluster = metadata.get("Cluster")
    if not isinstance(task_arn, str) or not isinstance(cluster, str) or not cluster:
        raise ECSDiscoveryError("SANDBOX_ECS_METADATA_IDENTITY_MISSING")
    match = _TASK_ARN.fullmatch(task_arn)
    if match is None:
        raise ECSDiscoveryError("SANDBOX_ECS_TASK_ARN_INVALID")
    account_id = match.group(1)

    ecs = boto3.client("ecs", region_name=region)
    try:
        response = ecs.describe_services(cluster=cluster, services=["sandbox-runtime"])
    except (BotoCoreError, ClientError) as exc:
        raise ECSDiscoveryError("SANDBOX_ECS_SERVICE_DISCOVERY_FAILED") from exc
    failures = response.get("failures", [])
    services = response.get("services", [])
    if failures or len(services) != 1 or not isinstance(services[0], dict):
        raise ECSDiscoveryError("SANDBOX_ECS_SERVICE_DISCOVERY_FAILED")
    network = services[0].get("networkConfiguration")
    awsvpc = network.get("awsvpcConfiguration") if isinstance(network, dict) else None
    if not isinstance(awsvpc, dict) or awsvpc.get("assignPublicIp") != "DISABLED":
        raise ECSDiscoveryError("SANDBOX_ECS_PRIVATE_NETWORK_REQUIRED")
    subnets = tuple(str(item) for item in awsvpc.get("subnets", []) if item)
    security_groups = tuple(str(item) for item in awsvpc.get("securityGroups", []) if item)
    if not subnets or not security_groups:
        raise ECSDiscoveryError("SANDBOX_ECS_PRIVATE_NETWORK_REQUIRED")

    child_family = f"lumi-{environment}-sandbox-child"
    try:
        child_definition = ecs.describe_task_definition(taskDefinition=child_family).get("taskDefinition")
    except (BotoCoreError, ClientError) as exc:
        raise ECSDiscoveryError("SANDBOX_CHILD_TASK_DEFINITION_MISSING") from exc
    if not isinstance(child_definition, dict) or child_definition.get("status") != "ACTIVE":
        raise ECSDiscoveryError("SANDBOX_CHILD_TASK_DEFINITION_MISSING")
    child_arn = child_definition.get("taskDefinitionArn")
    containers = child_definition.get("containerDefinitions", [])
    matches = [
        row
        for row in containers
        if isinstance(row, dict) and row.get("name") == "sandbox-child"
    ]
    if not isinstance(child_arn, str) or len(matches) != 1:
        raise ECSDiscoveryError("SANDBOX_CHILD_TASK_DEFINITION_INVALID")

    bucket = f"lumi-{environment}-{account_id}-{region}-sandbox"
    return ECSRemoteSandboxBackend(
        cluster=cluster,
        task_definition=child_arn,
        container="sandbox-child",
        subnets=subnets,
        security_groups=security_groups,
        exchange_bucket=bucket,
        region=region,
    )


def _task_metadata() -> dict[str, Any]:
    base = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "").rstrip("/")
    if not base.startswith("http://169.254.170.2/"):
        raise ECSDiscoveryError("SANDBOX_ECS_METADATA_URI_REQUIRED")
    request = urllib.request.Request(
        f"{base}/task",
        headers={"Accept": "application/json", "User-Agent": "LUMI-SandboxRuntime/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            body = response.read(128 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ECSDiscoveryError("SANDBOX_ECS_METADATA_UNAVAILABLE") from exc
    if len(body) > 128 * 1024:
        raise ECSDiscoveryError("SANDBOX_ECS_METADATA_TOO_LARGE")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ECSDiscoveryError("SANDBOX_ECS_METADATA_INVALID") from exc
    if not isinstance(payload, dict):
        raise ECSDiscoveryError("SANDBOX_ECS_METADATA_INVALID")
    return payload


def _required_env(name: str, *, fallback: str, max_length: int) -> str:
    value = os.getenv(name) or os.getenv(fallback, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise ECSDiscoveryError(f"{name}_REQUIRED")
    return value
