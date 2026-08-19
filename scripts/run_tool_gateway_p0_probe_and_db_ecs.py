#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from run_tool_gateway_p0_probe_ecs import (
    ECSProbeError,
    _CLUSTER,
    _CONTAINER,
    _LOG_GROUP,
    _LOG_PREFIX,
    _client,
    _container_exit,
    _discover_private_subnets,
    _discover_security_groups,
    _discover_vpc,
    _environment,
    _latest_task_definition,
    _required,
    _safe_task_summary,
    _task_id,
    _wait_task,
)

_PROBE_MARKER = "LUMI_TOOL_GATEWAY_P0_PROBE_JSON="
_DB_MARKER = "LUMI_TOOL_GATEWAY_P0_DB_EVIDENCE_JSON="
_DEFAULT_PROBE_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-probe.json"
_DEFAULT_DB_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-db-evidence.json"
_DEFAULT_TASK_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-ecs-task.json"


def _combined_command() -> list[str]:
    probe_path = "/tmp/tool-gateway-p0-probe.json"
    db_path = "/tmp/tool-gateway-p0-db-evidence.json"
    emit_probe = (
        "import json; "
        f"p=json.load(open('{probe_path}',encoding='utf-8')); "
        f"print('{_PROBE_MARKER}'+json.dumps(p,separators=(',',':'),sort_keys=True))"
    )
    emit_db = (
        "import json; "
        f"p=json.load(open('{db_path}',encoding='utf-8')); "
        f"print('{_DB_MARKER}'+json.dumps(p,separators=(',',':'),sort_keys=True))"
    )
    command = (
        f"LUMI_PROBE_OUTPUT={probe_path} "
        "python scripts/probe_tool_gateway_p0_from_agent_runtime.py"
        f" && LUMI_PROBE_INPUT={probe_path} LUMI_DB_EVIDENCE_OUTPUT={db_path} "
        "python scripts/collect_tool_gateway_p0_db_evidence.py"
        f" && python -c \"{emit_probe}\""
        f" && python -c \"{emit_db}\""
    )
    return ["/bin/sh", "-lc", command]


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
                    "command": _combined_command(),
                    "environment": environment,
                }
            ]
        },
        startedBy="node73-tool-gateway-p0-evidence",
    )
    failures = response.get("failures", [])
    if failures:
        raise ECSProbeError(f"ECS run_task failed: {json.dumps(failures, sort_keys=True)}")
    tasks = response.get("tasks", [])
    if len(tasks) != 1 or not isinstance(tasks[0], dict):
        raise ECSProbeError("ECS run_task did not return exactly one evidence task")
    task_arn = tasks[0].get("taskArn")
    if not isinstance(task_arn, str) or not task_arn:
        raise ECSProbeError("ECS evidence task ARN is missing")
    return task_arn


def _read_markers(
    logs: BaseClient,
    *,
    task_arn: str,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
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
            probe: dict[str, Any] | None = None
            db: dict[str, Any] | None = None
            for message in messages:
                if message.startswith(_PROBE_MARKER):
                    value = json.loads(message[len(_PROBE_MARKER) :])
                    if isinstance(value, dict):
                        probe = dict(value)
                elif message.startswith(_DB_MARKER):
                    value = json.loads(message[len(_DB_MARKER) :])
                    if isinstance(value, dict):
                        db = dict(value)
            if probe is not None and db is not None:
                return probe, db, messages
        except (ClientError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(3)
    detail = f": {last_error}" if last_error is not None else ""
    raise ECSProbeError(f"probe/DB evidence markers not found in CloudWatch logs{detail}")


def _write(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


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
    probe, db, messages = _read_markers(logs, task_arn=task_arn)

    _write(args.probe_output, probe)
    _write(args.db_output, db)
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
    _write(args.task_output, task_summary)
    if exit_code != 0:
        raise ECSProbeError(f"Agent Runtime evidence task exited {exit_code}: {reason}")
    return {
        "probe": args.probe_output,
        "db_evidence": args.db_output,
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
    parser.add_argument("--probe-output", default=_DEFAULT_PROBE_OUTPUT)
    parser.add_argument("--db-output", default=_DEFAULT_DB_OUTPUT)
    parser.add_argument("--task-output", default=_DEFAULT_TASK_OUTPUT)
    return parser


def main() -> int:
    try:
        result = run(_parser().parse_args())
    except (ECSProbeError, BotoCoreError, ClientError) as exc:
        raise SystemExit(f"Tool Gateway P0 ECS evidence run failed: {exc}") from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
