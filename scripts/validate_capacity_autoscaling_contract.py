#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ("staging", "production")
EXPECTED_SERVICES = (
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "outbox-dispatcher",
    "sandbox-runtime",
)
PHANTOM_METRICS = (
    "ApiConcurrentRequests",
    "AgentPendingRuns",
    "ModelGatewayInflight",
    "ToolGatewayInflight",
    "MediaQueueBacklog",
    "OutboxPendingEvents",
    "SandboxQueueBacklog",
)
OUTPUT_PATHS = (
    "infra/iac/modules/compute/outputs.tf",
    "infra/iac/modules/platform-app/outputs.tf",
    "infra/iac/environments/staging/app/outputs.tf",
    "infra/iac/environments/production/app/outputs.tf",
)
DECISION_PATHS = (
    "scripts/production-deployment-decision.py",
    "scripts/production-rollback-rehearsal-decision.py",
    "scripts/production-recovery-decision.py",
)


class ContractError(RuntimeError):
    pass


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise ContractError(f"missing {path}")
    return target.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def block(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise ContractError(f"missing block {marker!r}")
    brace = source.find("{", start)
    if brace < 0:
        raise ContractError(f"malformed block {marker!r}")
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ContractError(f"unterminated block {marker!r}")


def integer_attr(source: str, name: str) -> int:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*(\d+)\s*$", source)
    if match is None:
        raise ContractError(f"missing integer attribute {name}")
    return int(match.group(1))


def validate_environment_text(source: str, *, environment: str) -> None:
    require(
        source.count("autoscaling_enabled = false") == len(EXPECTED_SERVICES),
        f"{environment} must explicitly disable autoscaling for exactly seven services",
    )
    require("autoscaling_enabled = true" not in source, f"{environment} enables unmeasured autoscaling")
    for metric in PHANTOM_METRICS:
        require(metric not in source, f"{environment} still declares phantom metric {metric}")
    require("autoscale_metric_name" not in source, f"{environment} still declares autoscale_metric_name")
    require("autoscale_target_value" not in source, f"{environment} still declares autoscale_target_value")

    for service in EXPECTED_SERVICES:
        body = block(source, f"    {service} = {{")
        require(
            "autoscaling_enabled = false" in body,
            f"{environment} {service} must explicitly disable autoscaling",
        )
        desired = integer_attr(body, "desired_count")
        minimum = integer_attr(body, "min_capacity")
        maximum = integer_attr(body, "max_capacity")
        require(
            desired == minimum == maximum,
            f"{environment} {service} must be exact static capacity, got desired/min/max={desired}/{minimum}/{maximum}",
        )


def validate_module_contract() -> None:
    variables = read("infra/iac/modules/compute/variables.tf")
    compute = read("infra/iac/modules/compute/main.tf")

    for marker in (
        'autoscaling_enabled      = optional(bool, false)',
        'autoscale_metric_name    = optional(string, "")',
        'autoscale_target_value   = optional(number, 0)',
        "service.autoscaling_enabled == false",
        "service.desired_count == service.min_capacity",
        "service.desired_count == service.max_capacity",
        'service.autoscale_metric_name == ""',
        "service.autoscale_target_value == 0",
        "NODE-69 capacity is not measured yet",
    ):
        require(marker in variables, f"compute variables missing fail-closed marker {marker!r}")

    for marker in (
        "autoscaled_services = {",
        "for name, service in var.services : name => service if service.autoscaling_enabled",
        'resource "aws_appautoscaling_target" "service"',
        'resource "aws_appautoscaling_policy" "service_custom_metric"',
    ):
        require(marker in compute, f"compute module missing autoscaling gate marker {marker!r}")
    require(
        compute.count("for_each = local.autoscaled_services") == 2,
        "both autoscaling target and policy must be gated by local.autoscaled_services",
    )
    require("ignore_changes = [desired_count]" not in compute, "Terraform must own static desired_count")
    require(
        "LUMI emits queue/backlog/concurrency-aware custom metrics" not in compute,
        "compute module still claims an unproven capacity emitter",
    )


def validate_capacity_evidence_chain() -> None:
    for path in OUTPUT_PATHS:
        source = read(path)
        require("service_desired_counts" in source, f"{path} must propagate static desired counts")

    capture = read("scripts/capture-production-runtime-identity.sh")
    for marker in (
        "terraform -chdir=\"$APP_DIR\" output -json service_desired_counts",
        "Terraform expected capacity set does not match canonical seven-service contract",
        'EXPECTED_DESIRED="$(jq -r --arg name "$service"',
        "CAPACITY_MATCHED=false",
        'if [[ "$DESIRED" -eq "$EXPECTED_DESIRED" ]]',
        "expected_desired_count:$expected_desired_count",
        "capacity_matches:$capacity_matches",
    ):
        require(marker in capture, f"runtime capacity capture missing marker {marker!r}")

    for path in DECISION_PATHS:
        source = read(path)
        for marker in (
            "def _capacity_row_valid(",
            'item.get("expected_desired_count")',
            'item.get("desired_count")',
            'item.get("capacity_matches") is True',
        ):
            require(marker in source, f"{path} missing frozen capacity validation marker {marker!r}")

    readiness = read("scripts/validate_production_readiness_contract.py")
    recovery = read("scripts/validate_production_recovery_contract.py")
    for marker in (
        "dispatcher_rollforward_capacity_drift_blocked",
        "dispatcher_production_capacity_drift_blocked",
        "runtime_capacity_source_bound",
    ):
        require(marker in readiness, f"production readiness capacity drill missing {marker!r}")
    require(
        "dispatcher capacity identity mismatch" in recovery,
        "production recovery capacity negative drill missing",
    )


def validate_node69_release_state() -> None:
    node = read("docs/nodes/NODE-69-PERFORMANCE-SCALABILITY.md")
    plan = read("docs/performance/NODE-69-CAPACITY-PLAN.md")
    require("Status: SOURCE IMPLEMENTED / RELEASE BLOCKED" in node, "NODE-69 must remain release blocked")
    require("PENDING load evidence" in plan, "NODE-69 capacity plan must retain pending measured capacity")
    require("PENDING" in plan and "production-like Profile G" in plan, "NODE-69 measured release evidence is not explicit")
    require(
        "autoscaling_enabled = false" in plan and "Dynamic target tracking must remain disabled" in plan,
        "NODE-69 plan must explicitly keep dynamic autoscaling fail-closed",
    )


def validate_repo() -> None:
    validate_module_contract()
    for environment in ENVIRONMENTS:
        source = read(f"infra/iac/environments/{environment}/app/main.tf")
        validate_environment_text(source, environment=environment)
    validate_capacity_evidence_chain()
    validate_node69_release_state()


def self_test() -> None:
    staging = read("infra/iac/environments/staging/app/main.tf")
    mutations = (
        staging.replace("autoscaling_enabled = false", "autoscaling_enabled = true", 1),
        staging.replace("max_capacity        = 2", "max_capacity        = 3", 1),
        staging + '\n# autoscale_metric_name = "OutboxPendingEvents"\n',
    )
    for index, mutated in enumerate(mutations, start=1):
        try:
            validate_environment_text(mutated, environment=f"self-test-{index}")
        except ContractError:
            continue
        raise ContractError(f"negative drill {index} did not block")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate fail-closed ECS capacity/autoscaling contract")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    validate_repo()
    if args.self_test:
        self_test()
    print("capacity autoscaling contract: PASS (unmeasured signals remain static/fail-closed)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        raise SystemExit(f"capacity autoscaling contract invalid: {exc}") from exc
