#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]


class RuntimeClosureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeContract:
    name: str
    dockerfile: str
    entrypoint_sources: tuple[str, ...]
    expected_cmd_fragments: tuple[str, ...]
    required_source_fragments: tuple[tuple[str, str], ...] = ()
    forbidden_source_fragments: tuple[tuple[str, str], ...] = ()
    forbidden_fragments: tuple[str, ...] = (
        "sleep infinity",
        "sleep 365d",
        "tail -f /dev/null",
        "tail -f /dev/zero",
    )


RUNTIMES: tuple[RuntimeContract, ...] = (
    RuntimeContract(
        name="api",
        dockerfile="apps/api/Dockerfile",
        entrypoint_sources=("apps/api/src/lumi_api/cli.py", "apps/api/src/lumi_api/product_app.py"),
        expected_cmd_fragments=('CMD ["lumi-api"]',),
        required_source_fragments=(
            ("apps/api/src/lumi_api/cli.py", 'uvicorn.run("lumi_api.product_app:app"'),
        ),
    ),
    RuntimeContract(
        name="agent-runtime",
        dockerfile="apps/agent-runtime/Dockerfile",
        entrypoint_sources=(
            "apps/agent-runtime/src/lumi_agent_runtime/runtime_cli.py",
            "apps/agent-runtime/src/lumi_agent_runtime/runtime_service.py",
            "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/runtime_factory.py",
        ),
        expected_cmd_fragments=('CMD ["lumi-agent-runtime"]',),
        required_source_fragments=(
            (
                "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/runtime_factory.py",
                "class HostedDeepAgentRuntimeFactory",
            ),
            (
                "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/runtime_factory.py",
                "HttpProfileModelProvider.from_env()",
            ),
            (
                "apps/agent-runtime/src/lumi_agent_runtime/runtime_service.py",
                "HttpProfileModelProvider.from_env()",
            ),
            (
                "apps/agent-runtime/src/lumi_agent_runtime/runtime_service.py",
                "HttpToolGatewayTransport(",
            ),
            (
                "apps/agent-runtime/src/lumi_agent_runtime/runtime_service.py",
                "missing_execution_bindings",
            ),
            (
                "apps/agent-runtime/src/lumi_agent_runtime/runtime_service.py",
                "status_code=200 if ready else 503",
            ),
        ),
        forbidden_source_fragments=(
            ("apps/agent-runtime/src/lumi_agent_runtime/runtime_service.py", "subprocess"),
            ("apps/agent-runtime/src/lumi_agent_runtime/runtime_service.py", "docker.sock"),
        ),
    ),
    RuntimeContract(
        name="model-gateway",
        dockerfile="services/model-gateway/Dockerfile",
        entrypoint_sources=(
            "apps/api/src/lumi_api/model_gateway_cli.py",
            "apps/api/src/lumi_api/model_gateway_service.py",
            "apps/api/src/lumi_api/model_gateway_bootstrap.py",
        ),
        expected_cmd_fragments=("lumi_api.model_gateway_cli",),
    ),
    RuntimeContract(
        name="tool-gateway",
        dockerfile="services/tool-gateway/Dockerfile",
        entrypoint_sources=(
            "services/tool-gateway/src/lumi_tool_gateway/cli.py",
            "services/tool-gateway/src/lumi_tool_gateway/service.py",
            "services/tool-gateway/src/lumi_tool_gateway/http_transport.py",
            "services/tool-gateway/src/lumi_tool_gateway/sandbox_transport.py",
            "services/tool-gateway/src/lumi_tool_gateway/api.py",
            "services/tool-gateway/src/lumi_tool_gateway/gateway.py",
        ),
        expected_cmd_fragments=('CMD ["lumi-tool-gateway"]',),
        required_source_fragments=(
            ("services/tool-gateway/src/lumi_tool_gateway/api.py", "class ToolGatewayAPI"),
            ("services/tool-gateway/src/lumi_tool_gateway/gateway.py", "class ToolGateway"),
            (
                "services/tool-gateway/src/lumi_tool_gateway/http_transport.py",
                "hmac.compare_digest",
            ),
            (
                "services/tool-gateway/src/lumi_tool_gateway/http_transport.py",
                'service: str = "agent-runtime"',
            ),
            (
                "services/tool-gateway/src/lumi_tool_gateway/service.py",
                '_ALLOWED_CALLERS = frozenset({"agent-runtime"})',
            ),
            (
                "services/tool-gateway/src/lumi_tool_gateway/service.py",
                "_REQUIRED_RUNTIME_BINDINGS",
            ),
            (
                "services/tool-gateway/src/lumi_tool_gateway/service.py",
                "TOOL_GATEWAY_RUNTIME_NOT_READY",
            ),
            (
                "services/tool-gateway/src/lumi_tool_gateway/service.py",
                "SandboxExecuteAdapter(HttpSandboxExecutor.from_env())",
            ),
            (
                "services/tool-gateway/src/lumi_tool_gateway/service.py",
                "status_code=200 if ready else 503",
            ),
            (
                "services/tool-gateway/src/lumi_tool_gateway/sandbox_transport.py",
                '"X-Lumi-Service": "tool-gateway"',
            ),
        ),
    ),
    RuntimeContract(
        name="worker-media",
        dockerfile="apps/worker-media/Dockerfile",
        entrypoint_sources=(
            "apps/worker-media/src/lumi_worker_media/worker_cli.py",
            "apps/worker-media/src/lumi_worker_media/job_runtime.py",
            "apps/worker-media/src/lumi_worker_media/image_generation_runtime.py",
        ),
        expected_cmd_fragments=("lumi_worker_media.worker_cli",),
    ),
    RuntimeContract(
        name="sandbox-runtime",
        dockerfile="services/sandbox-runtime/Dockerfile",
        entrypoint_sources=(
            "services/sandbox-runtime/src/lumi_sandbox_runtime/cli.py",
            "services/sandbox-runtime/src/lumi_sandbox_runtime/service.py",
            "services/sandbox-runtime/src/lumi_sandbox_runtime/ports.py",
            "services/sandbox-runtime/src/lumi_sandbox_runtime/security.py",
        ),
        expected_cmd_fragments=('CMD ["lumi-sandbox-runtime"]',),
        required_source_fragments=(
            ("services/sandbox-runtime/src/lumi_sandbox_runtime/security.py", "class "),
            (
                "services/sandbox-runtime/src/lumi_sandbox_runtime/service.py",
                '_ALLOWED_CALLERS = frozenset({"tool-gateway"})',
            ),
            (
                "services/sandbox-runtime/src/lumi_sandbox_runtime/service.py",
                "hmac.compare_digest",
            ),
            (
                "services/sandbox-runtime/src/lumi_sandbox_runtime/service.py",
                "network_policy=NetworkPolicy.NONE",
            ),
            (
                "services/sandbox-runtime/src/lumi_sandbox_runtime/service.py",
                "status_code=200 if runtime.ready else 503",
            ),
            (
                "services/sandbox-runtime/src/lumi_sandbox_runtime/service.py",
                "LUMI_SANDBOX_RUNTIME_AUTH_SECRET",
            ),
            (
                "services/sandbox-runtime/src/lumi_sandbox_runtime/service.py",
                "def _build_production_backend()",
            ),
        ),
        forbidden_source_fragments=(
            ("services/sandbox-runtime/src/lumi_sandbox_runtime/service.py", "DockerBackend"),
            ("services/sandbox-runtime/src/lumi_sandbox_runtime/service.py", "LocalBackend"),
            ("services/sandbox-runtime/src/lumi_sandbox_runtime/service.py", "subprocess"),
            ("services/sandbox-runtime/src/lumi_sandbox_runtime/service.py", "docker.sock"),
        ),
    ),
)

_IAC_FILES = (
    "infra/iac/environments/staging/core/main.tf",
    "infra/iac/environments/production/core/main.tf",
    "infra/iac/environments/staging/app/main.tf",
    "infra/iac/environments/production/app/main.tf",
)


def _text(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise RuntimeClosureError(f"missing required runtime source: {relative}")
    return path.read_text(encoding="utf-8")


def _require_python_parses(relative: str) -> None:
    source = _text(relative)
    if not relative.endswith(".py"):
        return
    try:
        ast.parse(source, filename=relative)
    except SyntaxError as exc:
        raise RuntimeClosureError(f"runtime Python source does not parse: {relative}: {exc}") from exc


def _require_all(haystack: str, fragments: Iterable[str], *, label: str) -> None:
    for fragment in fragments:
        if fragment not in haystack:
            raise RuntimeClosureError(f"{label} missing required fragment: {fragment}")


def _validate_private_runtime_iac_boundary() -> None:
    staging_core = _text(_IAC_FILES[0])
    production_core = _text(_IAC_FILES[1])
    for label, source in (
        (_IAC_FILES[0], staging_core),
        (_IAC_FILES[1], production_core),
    ):
        _require_all(
            source,
            ('"internal/tool-gateway"', '"internal/sandbox-runtime"'),
            label=label,
        )

    for relative in _IAC_FILES[2:]:
        source = _text(relative)
        _require_all(
            source,
            (
                "LUMI_TOOL_GATEWAY_URL",
                "tool-gateway.${local.environment}.lumi.internal:8080",
                "LUMI_TOOL_GATEWAY_AUTH_SECRET",
                'local.secret_arns["internal/tool-gateway"]',
                "LUMI_SANDBOX_RUNTIME_URL",
                "sandbox-runtime.${local.environment}.lumi.internal:8080",
                "LUMI_SANDBOX_RUNTIME_AUTH_SECRET",
                'local.secret_arns["internal/sandbox-runtime"]',
            ),
            label=relative,
        )
        if source.count("LUMI_TOOL_GATEWAY_AUTH_SECRET") < 2:
            raise RuntimeClosureError(
                f"{relative} must inject the dedicated Tool Gateway secret into both "
                "agent-runtime and tool-gateway"
            )
        if source.count("LUMI_SANDBOX_RUNTIME_AUTH_SECRET") < 2:
            raise RuntimeClosureError(
                f"{relative} must inject the dedicated Sandbox secret into both "
                "tool-gateway and sandbox-runtime"
            )


def validate_runtime(contract: RuntimeContract) -> dict[str, object]:
    dockerfile = _text(contract.dockerfile)
    lowered = dockerfile.casefold()
    _require_all(dockerfile, contract.expected_cmd_fragments, label=contract.dockerfile)
    _require_all(
        dockerfile,
        (
            "python:3.12-slim",
            "uv sync --all-packages --frozen --no-dev",
            "USER 10001:10001",
        ),
        label=contract.dockerfile,
    )
    for forbidden in contract.forbidden_fragments:
        if forbidden in lowered:
            raise RuntimeClosureError(
                f"{contract.name} Dockerfile contains placeholder runtime command: {forbidden}"
            )

    for relative in contract.entrypoint_sources:
        _require_python_parses(relative)
    for relative, fragment in contract.required_source_fragments:
        source = _text(relative)
        if fragment not in source:
            raise RuntimeClosureError(
                f"{contract.name} production source {relative} missing boundary: {fragment}"
            )
    for relative, forbidden in contract.forbidden_source_fragments:
        source = _text(relative)
        if forbidden in source:
            raise RuntimeClosureError(
                f"{contract.name} production source {relative} contains forbidden boundary: "
                f"{forbidden}"
            )
    if contract.name in {"tool-gateway", "sandbox-runtime"}:
        _validate_private_runtime_iac_boundary()

    return {
        "runtime": contract.name,
        "dockerfile": contract.dockerfile,
        "entrypoint_sources": list(contract.entrypoint_sources),
        "status": "PASS",
    }


def main() -> int:
    results: list[dict[str, object]] = []
    blockers: list[str] = []
    for contract in RUNTIMES:
        try:
            results.append(validate_runtime(contract))
        except RuntimeClosureError as exc:
            blockers.append(f"{contract.name}: {exc}")
            results.append(
                {
                    "runtime": contract.name,
                    "dockerfile": contract.dockerfile,
                    "status": "BLOCKED",
                    "error": str(exc),
                }
            )
    payload = {
        "status": "PASS" if not blockers else "BLOCKED",
        "runtime_count": len(RUNTIMES),
        "passed": sum(1 for item in results if item["status"] == "PASS"),
        "blocked": len(blockers),
        "results": results,
        "blockers": blockers,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
