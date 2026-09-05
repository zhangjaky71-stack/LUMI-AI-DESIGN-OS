#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

_CLUSTER = "lumi-staging-cluster"
_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_FIXTURE_MARKER = "LUMI_TOOL_GATEWAY_P0_FIXTURE_JSON="
_PROBE_MARKER = "LUMI_TOOL_GATEWAY_P0_PROBE_JSON="
_DB_MARKER = "LUMI_TOOL_GATEWAY_P0_DB_EVIDENCE_JSON="
_READINESS_MARKER = "LUMI_TOOL_GATEWAY_P0_READINESS_JSON="

_DEFAULT_FIXTURE_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-fixture.json"
_DEFAULT_PROBE_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-probe.json"
_DEFAULT_DB_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-db-evidence.json"
_DEFAULT_READINESS_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-readiness.json"
_DEFAULT_RUNTIME_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-runtime-identity.json"
_DEFAULT_TASK_OUTPUT = "reports/staging-acceptance/runtime/tool-gateway-p0-ecs-tasks.json"


class StagingE2EError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ServiceRuntime:
    service: str
    task_definition: str
    container: str
    image: str
    network_configuration: dict[str, Any]
    log_group: str
    log_prefix: str

    def public_identity(self) -> dict[str, Any]:
        awsvpc = self.network_configuration.get("awsvpcConfiguration", {})
        return {
            "service": self.service,
            "task_definition": self.task_definition,
            "container": self.container,
            "image": self.image,
            "image_is_immutable": bool(_IMAGE.fullmatch(self.image)),
            "assign_public_ip": awsvpc.get("assignPublicIp"),
            "subnet_count": len(awsvpc.get("subnets", [])),
            "security_group_count": len(awsvpc.get("securityGroups", [])),
            "log_group": self.log_group,
            "log_prefix": self.log_prefix,
        }


def _client(name: str, region: str) -> BaseClient:
    return boto3.client(name, region_name=region)


def _required(value: str | None, label: str, *, max_length: int = 4096) -> str:
    if not value or len(value) > max_length or "\x00" in value:
        raise StagingE2EError(f"{label} is required")
    return value


def _release_sha(value: str) -> str:
    if not _SHA40.fullmatch(value):
        raise StagingE2EError("release_git_sha must be an exact 40-character lowercase SHA")
    return value


def _expected_image(value: str | None, label: str) -> str | None:
    if value in {None, ""}:
        return None
    assert value is not None
    if not _IMAGE.fullmatch(value):
        raise StagingE2EError(f"{label} must be digest-pinned")
    return value


def _service_runtime(ecs: BaseClient, service: str) -> ServiceRuntime:
    response = ecs.describe_services(cluster=_CLUSTER, services=[service])
    failures = response.get("failures", [])
    if failures:
        raise StagingE2EError(
            f"ECS service lookup failed for {service}: {json.dumps(failures, sort_keys=True)}"
        )
    services = response.get("services", [])
    if len(services) != 1 or not isinstance(services[0], dict):
        raise StagingE2EError(f"expected exactly one deployed ECS service: {service}")
    row = services[0]
    if row.get("status") != "ACTIVE":
        raise StagingE2EError(f"ECS service is not ACTIVE: {service}")
    task_definition = row.get("taskDefinition")
    if not isinstance(task_definition, str) or not task_definition:
        raise StagingE2EError(f"ECS service task definition is missing: {service}")
    network = row.get("networkConfiguration")
    if not isinstance(network, dict):
        raise StagingE2EError(f"ECS service network configuration is missing: {service}")
    awsvpc = network.get("awsvpcConfiguration")
    if not isinstance(awsvpc, dict):
        raise StagingE2EError(f"ECS service awsvpc configuration is missing: {service}")
    if awsvpc.get("assignPublicIp") != "DISABLED":
        raise StagingE2EError(f"ECS service must disable public IPs: {service}")
    if not isinstance(awsvpc.get("subnets"), list) or not awsvpc["subnets"]:
        raise StagingE2EError(f"ECS service has no private subnets: {service}")
    if not isinstance(awsvpc.get("securityGroups"), list) or not awsvpc["securityGroups"]:
        raise StagingE2EError(f"ECS service has no security groups: {service}")

    definition = ecs.describe_task_definition(taskDefinition=task_definition).get("taskDefinition")
    if not isinstance(definition, dict):
        raise StagingE2EError(f"ECS task definition is unavailable: {service}")
    containers = definition.get("containerDefinitions", [])
    matches = [
        item
        for item in containers
        if isinstance(item, dict) and item.get("name") == service
    ]
    if len(matches) != 1:
        raise StagingE2EError(f"ECS task definition must contain one {service} container")
    container = matches[0]
    image = container.get("image")
    if not isinstance(image, str) or not _IMAGE.fullmatch(image):
        raise StagingE2EError(f"deployed {service} image must be immutable @sha256")
    log_configuration = container.get("logConfiguration")
    if not isinstance(log_configuration, dict) or log_configuration.get("logDriver") != "awslogs":
        raise StagingE2EError(f"deployed {service} container must use awslogs")
    options = log_configuration.get("options")
    if not isinstance(options, dict):
        raise StagingE2EError(f"deployed {service} awslogs options are missing")
    log_group = options.get("awslogs-group")
    log_prefix = options.get("awslogs-stream-prefix")
    if not isinstance(log_group, str) or not log_group:
        raise StagingE2EError(f"deployed {service} log group is missing")
    if not isinstance(log_prefix, str) or not log_prefix:
        raise StagingE2EError(f"deployed {service} log prefix is missing")
    return ServiceRuntime(
        service=service,
        task_definition=task_definition,
        container=service,
        image=image,
        network_configuration=network,
        log_group=log_group,
        log_prefix=log_prefix,
    )


def _require_expected(runtime: ServiceRuntime, expected: str | None) -> None:
    if expected is not None and runtime.image != expected:
        raise StagingE2EError(
            f"deployed {runtime.service} image differs from requested RC image"
        )


def _run_task(
    ecs: BaseClient,
    runtime: ServiceRuntime,
    *,
    command: list[str],
    environment: dict[str, str] | None,
    started_by: str,
) -> str:
    override: dict[str, Any] = {
        "name": runtime.container,
        "command": command,
    }
    if environment:
        override["environment"] = [
            {"name": key, "value": value} for key, value in sorted(environment.items())
        ]
    response = ecs.run_task(
        cluster=_CLUSTER,
        taskDefinition=runtime.task_definition,
        launchType="FARGATE",
        count=1,
        networkConfiguration=runtime.network_configuration,
        overrides={"containerOverrides": [override]},
        startedBy=started_by[:36],
    )
    failures = response.get("failures", [])
    if failures:
        raise StagingE2EError(f"ECS run_task failed: {json.dumps(failures, sort_keys=True)}")
    tasks = response.get("tasks", [])
    if len(tasks) != 1 or not isinstance(tasks[0], dict):
        raise StagingE2EError("ECS run_task did not return exactly one task")
    arn = tasks[0].get("taskArn")
    if not isinstance(arn, str) or not arn:
        raise StagingE2EError("ECS one-shot task ARN is missing")
    return arn


def _wait_task(ecs: BaseClient, task_arn: str) -> dict[str, Any]:
    ecs.get_waiter("tasks_stopped").wait(
        cluster=_CLUSTER,
        tasks=[task_arn],
        WaiterConfig={"Delay": 6, "MaxAttempts": 100},
    )
    response = ecs.describe_tasks(cluster=_CLUSTER, tasks=[task_arn])
    failures = response.get("failures", [])
    if failures:
        raise StagingE2EError(f"ECS describe_tasks failed: {json.dumps(failures, sort_keys=True)}")
    tasks = response.get("tasks", [])
    if len(tasks) != 1 or not isinstance(tasks[0], dict):
        raise StagingE2EError("stopped ECS one-shot task is missing")
    return dict(tasks[0])


def _task_id(task_arn: str) -> str:
    value = task_arn.rsplit("/", 1)[-1]
    if not value:
        raise StagingE2EError("ECS task id is invalid")
    return value


def _container_exit(task: dict[str, Any], container_name: str) -> tuple[int, str]:
    containers = task.get("containers", [])
    for container in containers if isinstance(containers, list) else []:
        if not isinstance(container, dict) or container.get("name") != container_name:
            continue
        exit_code = container.get("exitCode")
        if not isinstance(exit_code, int):
            raise StagingE2EError(f"{container_name} one-shot task has no exit code")
        reason = str(container.get("reason") or task.get("stoppedReason") or "")
        return exit_code, reason
    raise StagingE2EError(f"{container_name} one-shot task container result is missing")


def _log_stream(runtime: ServiceRuntime, task_arn: str) -> str:
    return f"{runtime.log_prefix}/{runtime.container}/{_task_id(task_arn)}"


def _read_markers(
    logs: BaseClient,
    runtime: ServiceRuntime,
    task_arn: str,
    markers: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], int]:
    stream = _log_stream(runtime, task_arn)
    deadline = time.monotonic() + 120
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = logs.get_log_events(
                logGroupName=runtime.log_group,
                logStreamName=stream,
                startFromHead=True,
            )
            events = response.get("events", [])
            messages = [str(item.get("message", "")) for item in events if isinstance(item, dict)]
            found: dict[str, dict[str, Any]] = {}
            for message in messages:
                for key, marker in markers.items():
                    if message.startswith(marker):
                        payload = json.loads(message[len(marker) :])
                        if not isinstance(payload, dict):
                            raise StagingE2EError(f"{key} marker payload must be an object")
                        found[key] = dict(payload)
            if set(found) == set(markers):
                return found, len(messages)
        except (ClientError, json.JSONDecodeError, StagingE2EError) as exc:
            last_error = exc
        time.sleep(3)
    detail = f": {last_error}" if last_error is not None else ""
    raise StagingE2EError(f"required CloudWatch evidence markers not found{detail}")


def _fixture_command() -> list[str]:
    return ["python", "-m", "lumi_api.tool_gateway_staging_fixture"]


def _agent_command() -> list[str]:
    probe = "/tmp/tool-gateway-p0-probe.json"
    db = "/tmp/tool-gateway-p0-db-evidence.json"
    readiness = "/tmp/tool-gateway-p0-readiness.json"

    def emit(path: str, marker: str) -> str:
        return (
            "import json; "
            f"p=json.load(open('{path}',encoding='utf-8')); "
            f"print('{marker}'+json.dumps(p,separators=(',',':'),sort_keys=True))"
        )

    command = (
        f"LUMI_PROBE_OUTPUT={probe} python scripts/probe_tool_gateway_p0_from_agent_runtime.py"
        f" && LUMI_PROBE_INPUT={probe} LUMI_DB_EVIDENCE_OUTPUT={db} "
        "python scripts/collect_tool_gateway_p0_db_evidence.py"
        f" && LUMI_READINESS_EVIDENCE_OUTPUT={readiness} "
        "python scripts/collect_tool_gateway_p0_readiness.py"
        f" && python -c \"{emit(probe, _PROBE_MARKER)}\""
        f" && python -c \"{emit(db, _DB_MARKER)}\""
        f" && python -c \"{emit(readiness, _READINESS_MARKER)}\""
    )
    return ["/bin/sh", "-lc", command]


def _fixture_scope(fixture: dict[str, Any]) -> dict[str, str]:
    if fixture.get("schema_version") != 1:
        raise StagingE2EError("fixture schema_version must be 1")
    if fixture.get("synthetic_only") is not True:
        raise StagingE2EError("fixture must be synthetic_only=true")
    result: dict[str, str] = {}
    for key in (
        "organization_id",
        "project_id",
        "agent_run_id",
        "task_id",
        "source_asset_id",
        "artifact_id",
    ):
        value = fixture.get(key)
        if not isinstance(value, str):
            raise StagingE2EError(f"fixture {key} is missing")
        try:
            result[key] = str(UUID(value))
        except ValueError as exc:
            raise StagingE2EError(f"fixture {key} must be a UUID") from exc
    return result


def _agent_environment(
    scope: dict[str, str],
    *,
    idempotency_key: str,
    trace_prefix: str,
    search_query: str,
    fetch_url: str,
) -> dict[str, str]:
    return {
        "LUMI_PROBE_ORGANIZATION_ID": scope["organization_id"],
        "LUMI_PROBE_AGENT_RUN_ID": scope["agent_run_id"],
        "LUMI_PROBE_TASK_ID": scope["task_id"],
        "LUMI_PROBE_SOURCE_ASSET_ID": scope["source_asset_id"],
        "LUMI_PROBE_ARTIFACT_ID": scope["artifact_id"],
        "LUMI_PROBE_DERIVED_IDEMPOTENCY_KEY": idempotency_key,
        "LUMI_PROBE_TRACE_PREFIX": trace_prefix,
        "LUMI_PROBE_SEARCH_QUERY": search_query,
        "LUMI_PROBE_FETCH_URL": fetch_url,
    }


def _task_summary(
    runtime: ServiceRuntime,
    task: dict[str, Any],
    *,
    exit_code: int,
    reason: str,
    log_event_count: int,
) -> dict[str, Any]:
    return {
        "service": runtime.service,
        "task_arn": task.get("taskArn"),
        "task_definition": runtime.task_definition,
        "image": runtime.image,
        "launch_type": task.get("launchType"),
        "platform_version": task.get("platformVersion"),
        "availability_zone": task.get("availabilityZone"),
        "started_by": task.get("startedBy"),
        "stopped_reason": task.get("stoppedReason"),
        "container_exit_code": exit_code,
        "container_reason": reason,
        "cloudwatch_log_group": runtime.log_group,
        "cloudwatch_log_stream": _log_stream(runtime, str(task.get("taskArn", ""))),
        "captured_log_event_count": log_event_count,
    }


def _write(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    region = _required(args.region or os.getenv("AWS_REGION"), "AWS region", max_length=64)
    release_git_sha = _release_sha(args.release_git_sha)
    ecs = _client("ecs", region)
    logs = _client("logs", region)

    runtimes = {
        name: _service_runtime(ecs, name)
        for name in ("api", "agent-runtime", "tool-gateway", "sandbox-runtime")
    }
    expected = {
        "api": _expected_image(args.expected_api_image, "expected_api_image"),
        "agent-runtime": _expected_image(
            args.expected_agent_runtime_image,
            "expected_agent_runtime_image",
        ),
        "tool-gateway": _expected_image(
            args.expected_tool_gateway_image,
            "expected_tool_gateway_image",
        ),
        "sandbox-runtime": _expected_image(
            args.expected_sandbox_runtime_image,
            "expected_sandbox_runtime_image",
        ),
    }
    for name, runtime in runtimes.items():
        _require_expected(runtime, expected[name])

    run_token = uuid4().hex
    fixture_arn = _run_task(
        ecs,
        runtimes["api"],
        command=_fixture_command(),
        environment=None,
        started_by=f"node73-fixture-{run_token}",
    )
    fixture_task = _wait_task(ecs, fixture_arn)
    fixture_exit, fixture_reason = _container_exit(fixture_task, "api")
    if fixture_exit != 0:
        raise StagingE2EError(f"API fixture task exited {fixture_exit}: {fixture_reason}")
    fixture_markers, fixture_log_count = _read_markers(
        logs,
        runtimes["api"],
        fixture_arn,
        {"fixture": _FIXTURE_MARKER},
    )
    fixture = fixture_markers["fixture"]
    scope = _fixture_scope(fixture)

    idempotency_key = f"node73-tool-gateway-p0-{run_token}"
    trace_prefix = f"node73-tool-gateway-p0-{run_token}"
    agent_arn = _run_task(
        ecs,
        runtimes["agent-runtime"],
        command=_agent_command(),
        environment=_agent_environment(
            scope,
            idempotency_key=idempotency_key,
            trace_prefix=trace_prefix,
            search_query=_required(args.search_query, "search_query", max_length=400),
            fetch_url=_required(args.fetch_url, "fetch_url", max_length=4096),
        ),
        started_by=f"node73-probe-{run_token}",
    )
    agent_task = _wait_task(ecs, agent_arn)
    agent_exit, agent_reason = _container_exit(agent_task, "agent-runtime")
    if agent_exit != 0:
        raise StagingE2EError(
            f"Agent Runtime Tool Gateway evidence task exited {agent_exit}: {agent_reason}"
        )
    agent_markers, agent_log_count = _read_markers(
        logs,
        runtimes["agent-runtime"],
        agent_arn,
        {
            "probe": _PROBE_MARKER,
            "db": _DB_MARKER,
            "readiness": _READINESS_MARKER,
        },
    )

    _write(args.fixture_output, fixture)
    _write(args.probe_output, agent_markers["probe"])
    _write(args.db_output, agent_markers["db"])
    _write(args.readiness_output, agent_markers["readiness"])
    runtime_identity = {
        "schema_version": 1,
        "environment": "staging",
        "release_git_sha": release_git_sha,
        "cluster": _CLUSTER,
        "synthetic_only": True,
        "services": {name: runtime.public_identity() for name, runtime in runtimes.items()},
    }
    _write(args.runtime_output, runtime_identity)
    tasks = {
        "schema_version": 1,
        "release_git_sha": release_git_sha,
        "fixture": _task_summary(
            runtimes["api"],
            fixture_task,
            exit_code=fixture_exit,
            reason=fixture_reason,
            log_event_count=fixture_log_count,
        ),
        "probe": _task_summary(
            runtimes["agent-runtime"],
            agent_task,
            exit_code=agent_exit,
            reason=agent_reason,
            log_event_count=agent_log_count,
        ),
    }
    _write(args.task_output, tasks)
    return {
        "fixture": args.fixture_output,
        "probe": args.probe_output,
        "db_evidence": args.db_output,
        "readiness": args.readiness_output,
        "runtime_identity": args.runtime_output,
        "tasks": args.task_output,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="")
    parser.add_argument("--release-git-sha", required=True)
    parser.add_argument("--expected-api-image", default="")
    parser.add_argument("--expected-agent-runtime-image", default="")
    parser.add_argument("--expected-tool-gateway-image", default="")
    parser.add_argument("--expected-sandbox-runtime-image", default="")
    parser.add_argument("--search-query", default="LUMI design systems")
    parser.add_argument("--fetch-url", default="https://example.com/")
    parser.add_argument("--fixture-output", default=_DEFAULT_FIXTURE_OUTPUT)
    parser.add_argument("--probe-output", default=_DEFAULT_PROBE_OUTPUT)
    parser.add_argument("--db-output", default=_DEFAULT_DB_OUTPUT)
    parser.add_argument("--readiness-output", default=_DEFAULT_READINESS_OUTPUT)
    parser.add_argument("--runtime-output", default=_DEFAULT_RUNTIME_OUTPUT)
    parser.add_argument("--task-output", default=_DEFAULT_TASK_OUTPUT)
    return parser


def main() -> int:
    try:
        result = run(_parser().parse_args())
    except (StagingE2EError, BotoCoreError, ClientError) as exc:
        raise SystemExit(f"Tool Gateway P0 staging ECS run failed: {exc}") from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
