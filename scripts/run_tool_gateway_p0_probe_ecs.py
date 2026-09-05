#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

_PROJECT = "lumi"
_ENVIRONMENT = "staging"
_CLUSTER = "lumi-staging-cluster"
_TASK_FAMILY = "lumi-staging-agent-runtime"
_CONTAINER = "agent-runtime"
_LOG_GROUP = "/lumi/staging/agent-runtime"
_LOG_PREFIX = "agent-runtime"
_RESULT_MARKER = "LUMI_TOOL_GATEWAY_P0_PROBE_JSON="
_DEFAULT_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-probe.json"
_DEFAULT_TASK_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-ecs-task.json"


class ECSProbeError(RuntimeError):
    pass


def _uuid(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ECSProbeError(f"{label} must be a UUID") from exc


def _required(value: str | None, label: str, *, max_length: int = 4096) -> str:
    if not value or len(value) > max_length or "\x00" in value:
        raise ECSProbeError(f"{label} is required")
    return value


def _client(name: str, *, region: str) -> BaseClient:
    return boto3.client(name, region_name=region)


def _discover_vpc(ec2: BaseClient) -> str:
    response = ec2.describe_vpcs(
        Filters=[
            {"Name": "tag:Project", "Values": [_PROJECT]},
            {"Name": "tag:Environment", "Values": [_ENVIRONMENT]},
            {"Name": "tag:ManagedBy", "Values": ["terraform"]},
        ]
    )
    rows = response.get("Vpcs", [])
    if len(rows) != 1:
        raise ECSProbeError(f"expected exactly one staging VPC, found {len(rows)}")
    vpc_id = rows[0].get("VpcId")
    if not isinstance(vpc_id, str) or not vpc_id:
        raise ECSProbeError("staging VPC has no VpcId")
    return vpc_id


def _tag_name(row: dict[str, Any]) -> str:
    tags = row.get("Tags", [])
    if not isinstance(tags, list):
        return ""
    for tag in tags:
        if isinstance(tag, dict) and tag.get("Key") == "Name":
            value = tag.get("Value")
            return value if isinstance(value, str) else ""
    return ""


def _discover_private_subnets(ec2: BaseClient, *, vpc_id: str) -> list[str]:
    response = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    rows = response.get("Subnets", [])
    selected: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _tag_name(row)
        subnet_id = row.get("SubnetId")
        if name.startswith("lumi-staging-private-") and isinstance(subnet_id, str):
            selected.append(subnet_id)
    selected.sort()
    if len(selected) < 2:
        raise ECSProbeError(
            f"expected at least two staging private subnets, found {len(selected)}"
        )
    return selected


def _discover_security_groups(ec2: BaseClient, *, vpc_id: str) -> list[str]:
    names = ["lumi-staging-app", "lumi-staging-app-internet-egress"]
    response = ec2.describe_security_groups(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "group-name", "Values": names},
        ]
    )
    rows = response.get("SecurityGroups", [])
    found: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("GroupName")
        group_id = row.get("GroupId")
        if isinstance(name, str) and isinstance(group_id, str):
            found[name] = group_id
    missing = [name for name in names if name not in found]
    if missing:
        raise ECSProbeError(f"missing staging security groups: {', '.join(missing)}")
    return [found[name] for name in names]


def _latest_task_definition(ecs: BaseClient) -> str:
    response = ecs.list_task_definitions(
        familyPrefix=_TASK_FAMILY,
        status="ACTIVE",
        sort="DESC",
        maxResults=10,
    )
    rows = response.get("taskDefinitionArns", [])
    if not rows:
        raise ECSProbeError(f"no active ECS task definition for {_TASK_FAMILY}")
    arn = rows[0]
    if not isinstance(arn, str) or not arn:
        raise ECSProbeError("latest Agent Runtime task definition ARN is invalid")
    return arn


def _probe_command() -> list[str]:
    probe_path = "/tmp/tool-gateway-p0-probe.json"
    marker_script = (
        "import json; "
        f"p=json.load(open('{probe_path}',encoding='utf-8')); "
        f"print('{_RESULT_MARKER}'+json.dumps(p,separators=(',',':'),sort_keys=True))"
    )
    command = (
        f"LUMI_PROBE_OUTPUT={probe_path} "
        "python scripts/probe_tool_gateway_p0_from_agent_runtime.py"
        f" && python -c \"{marker_script}\""
    )
    return ["/bin/sh", "-lc", command]


def _environment(args: argparse.Namespace) -> list[dict[str, str]]:
    values = {
        "LUMI_PROBE_ORGANIZATION_ID": _uuid(args.organization_id, "organization_id"),
        "LUMI_PROBE_AGENT_RUN_ID": _uuid(args.agent_run_id, "agent_run_id"),
        "LUMI_PROBE_TASK_ID": _uuid(args.task_id, "task_id"),
        "LUMI_PROBE_SOURCE_ASSET_ID": _uuid(args.source_asset_id, "source_asset_id"),
        "LUMI_PROBE_ARTIFACT_ID": _uuid(args.artifact_id, "artifact_id"),
        "LUMI_PROBE_DERIVED_IDEMPOTENCY_KEY": _required(
            args.idempotency_key,
            "idempotency_key",
            max_length=256,
        ),
        "LUMI_PROBE_SEARCH_QUERY": _required(
            args.search_query,
            "search_query",
            max_length=400,
        ),
        "LUMI_PROBE_FETCH_URL": _required(args.fetch_url, "fetch_url", max_length=4096),
        "LUMI_PROBE_TRACE_PREFIX": _required(
            args.trace_prefix,
            "trace_prefix",
            max_length=256,
        ),
    }
    return [{"name": key, "value": value} for key, value in sorted(values.items())]


def _run_task(
    ecs: BaseClient,
    *,
    task_definition: str,
    subnets: list[str],
    security_groups: list[str],
    environment: list[dict[str, str]],
) -> str:
    response = ecs.run_task(
        cluster=_CLUSTER,
        taskDefinition=task_definition,
        launchType="FARGATE",
        count=1,
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": subnets,
                "securityGroups": security_groups,
                "assignPublicIp": "DISABLED",
            }
        },
        overrides={
            "containerOverrides": [
                {
                    "name": _CONTAINER,
                    "command": _probe_command(),
                    "environment": environment,
                }
            ]
        },
        startedBy="node73-tool-gateway-p0-e2e",
    )
    failures = response.get("failures", [])
    if failures:
        raise ECSProbeError(f"ECS run_task failed: {json.dumps(failures, sort_keys=True)}")
    tasks = response.get("tasks", [])
    if len(tasks) != 1 or not isinstance(tasks[0], dict):
        raise ECSProbeError("ECS run_task did not return exactly one task")
    task_arn = tasks[0].get("taskArn")
    if not isinstance(task_arn, str) or not task_arn:
        raise ECSProbeError("ECS task ARN is missing")
    return task_arn


def _wait_task(ecs: BaseClient, *, task_arn: str) -> dict[str, Any]:
    waiter = ecs.get_waiter("tasks_stopped")
    waiter.wait(
        cluster=_CLUSTER,
        tasks=[task_arn],
        WaiterConfig={"Delay": 6, "MaxAttempts": 100},
    )
    response = ecs.describe_tasks(cluster=_CLUSTER, tasks=[task_arn])
    tasks = response.get("tasks", [])
    if len(tasks) != 1 or not isinstance(tasks[0], dict):
        raise ECSProbeError("stopped ECS probe task is missing")
    return dict(tasks[0])


def _container_exit(task: dict[str, Any]) -> tuple[int, str]:
    containers = task.get("containers", [])
    for container in containers if isinstance(containers, list) else []:
        if not isinstance(container, dict) or container.get("name") != _CONTAINER:
            continue
        exit_code = container.get("exitCode")
        reason = str(container.get("reason") or task.get("stoppedReason") or "")
        if not isinstance(exit_code, int):
            raise ECSProbeError("Agent Runtime probe container has no exit code")
        return exit_code, reason
    raise ECSProbeError("Agent Runtime probe container result is missing")


def _task_id(task_arn: str) -> str:
    value = task_arn.rsplit("/", 1)[-1]
    if not value:
        raise ECSProbeError("ECS task id is invalid")
    return value


def _read_probe_log(logs: BaseClient, *, task_arn: str) -> tuple[dict[str, Any], list[str]]:
    stream = f"{_LOG_PREFIX}/{_CONTAINER}/{_task_id(task_arn)}"
    deadline = time.monotonic() + 120
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = logs.get_log_events(
                logGroupName=_LOG_GROUP,
                logStreamName=stream,
                startFromHead=True,
            )
            events = response.get("events", [])
            messages = [
                str(event.get("message", ""))
                for event in events
                if isinstance(event, dict)
            ]
            for message in messages:
                if message.startswith(_RESULT_MARKER):
                    raw = message[len(_RESULT_MARKER) :]
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise ECSProbeError("probe log marker payload is not an object")
                    return dict(payload), messages
        except (ClientError, json.JSONDecodeError, ECSProbeError) as exc:
            last_error = exc
        time.sleep(3)
    detail = f": {last_error}" if last_error is not None else ""
    raise ECSProbeError(f"probe result marker not found in CloudWatch logs{detail}")


def _safe_task_summary(task: dict[str, Any], *, task_definition: str) -> dict[str, Any]:
    return {
        "cluster": _CLUSTER,
        "task_arn": task.get("taskArn"),
        "task_definition": task_definition,
        "launch_type": task.get("launchType"),
        "platform_version": task.get("platformVersion"),
        "availability_zone": task.get("availabilityZone"),
        "stopped_reason": task.get("stoppedReason"),
        "started_by": task.get("startedBy"),
        "connectivity": task.get("connectivity"),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    region = _required(args.region or os.getenv("AWS_REGION"), "AWS region", max_length=64)
    ecs = _client("ecs", region=region)
    ec2 = _client("ec2", region=region)
    logs = _client("logs", region=region)

    vpc_id = _discover_vpc(ec2)
    subnets = _discover_private_subnets(ec2, vpc_id=vpc_id)
    security_groups = _discover_security_groups(ec2, vpc_id=vpc_id)
    task_definition = _latest_task_definition(ecs)
    task_arn = _run_task(
        ecs,
        task_definition=task_definition,
        subnets=subnets,
        security_groups=security_groups,
        environment=_environment(args),
    )
    task = _wait_task(ecs, task_arn=task_arn)
    exit_code, reason = _container_exit(task)
    probe, messages = _read_probe_log(logs, task_arn=task_arn)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(probe, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    task_summary = _safe_task_summary(task, task_definition=task_definition)
    task_summary.update(
        {
            "region": region,
            "vpc_id": vpc_id,
            "private_subnet_ids": subnets,
            "security_group_ids": security_groups,
            "container_exit_code": exit_code,
            "container_reason": reason,
            "cloudwatch_log_group": _LOG_GROUP,
            "cloudwatch_log_stream": f"{_LOG_PREFIX}/{_CONTAINER}/{_task_id(task_arn)}",
            "captured_log_event_count": len(messages),
        }
    )
    Path(args.task_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.task_output).write_text(
        json.dumps(task_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if exit_code != 0:
        raise ECSProbeError(f"Agent Runtime probe exited {exit_code}: {reason}")
    return {
        "probe": args.output,
        "task": args.task_output,
        "task_arn": task_arn,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="")
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--agent-run-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source-asset-id", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--search-query", default="LUMI design systems")
    parser.add_argument("--fetch-url", default="https://example.com/")
    parser.add_argument("--trace-prefix", default="node73-tool-gateway-p0")
    parser.add_argument("--output", default=_DEFAULT_OUTPUT)
    parser.add_argument("--task-output", default=_DEFAULT_TASK_OUTPUT)
    return parser


def main() -> int:
    try:
        result = run(_parser().parse_args())
    except (ECSProbeError, BotoCoreError, ClientError) as exc:
        raise SystemExit(f"Tool Gateway P0 ECS probe failed: {exc}") from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
