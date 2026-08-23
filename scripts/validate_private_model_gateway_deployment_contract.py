#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_PATH = "scripts/validate_private_model_gateway_deployment_contract.py"
ARCHITECTURE_CONTRACT = "scripts/validate_model_gateway_contract.py"
STAGING_APP = "infra/iac/environments/staging/app/main.tf"
PRODUCTION_APP = "infra/iac/environments/production/app/main.tf"
COMPUTE = "infra/iac/modules/compute/main.tf"
AGENT_CLIENT = "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/model_gateway_chat.py"
AGENT_FACTORY = "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime/runtime_factory.py"
IMAGE_CLIENT = "apps/worker-media/src/lumi_worker_media/image_gateway_runtime.py"
VIDEO_CLIENT = "apps/worker-media/src/lumi_worker_media/video_gateway_runtime.py"
GATEWAY_SERVICE = "apps/api/src/lumi_api/model_gateway_service.py"
RUNTIME_MANIFEST = "production/runtime-images/manifest-v1.json"
MODEL_WORKFLOW = ".github/workflows/model-gateway.yml"
IAC_WORKFLOW = ".github/workflows/production-iac-contract.yml"
STAGING_WORKFLOW = ".github/workflows/staging-acceptance-gate.yml"
FINAL_WORKFLOW = ".github/workflows/final-acceptance-gate.yml"

PROVIDER_SECRET_MARKERS = (
    "LUMI_MODEL_PROVIDER_SECRET",
    "LUMI_MEDIA_PROVIDER_SECRET",
)
RAW_PROVIDER_CREDENTIAL_MARKERS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "COHERE_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "REPLICATE_API_TOKEN",
    "FAL_KEY",
    "TOGETHER_API_KEY",
)


class ContractError(RuntimeError):
    pass


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise ContractError(f"missing source: {path}")
    return target.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_markers(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    require(not missing, f"{label} missing markers: {missing}")


def forbid_markers(source: str, markers: tuple[str, ...], label: str) -> None:
    present = [marker for marker in markers if marker in source]
    require(not present, f"{label} contains forbidden markers: {present}")


def hcl_block(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise ContractError(f"missing HCL block: {marker}")
    brace = source.find("{", start)
    if brace < 0:
        raise ContractError(f"malformed HCL block: {marker}")
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise ContractError(f"unterminated HCL block: {marker}")


def require_hcl_assignment(block: str, key: str, value: str, label: str) -> None:
    pattern = rf"(?m)^\s*{re.escape(key)}\s*=\s*{re.escape(value)}\s*(?:#.*)?$"
    require(re.search(pattern, block) is not None, label)


def validate_environment(app_path: str, *, environment: str) -> None:
    app = read(app_path)
    gateway_env = hcl_block(app, "model_gateway_environment = {")
    require_hcl_assignment(
        gateway_env,
        "LUMI_MODEL_GATEWAY_URL",
        '"http://model-gateway.${local.environment}.lumi.internal:8080"',
        f"{environment}: private Model Gateway service-discovery URL missing",
    )

    service_names = (
        "api",
        "agent-runtime",
        "model-gateway",
        "tool-gateway",
        "worker-media",
        "outbox-dispatcher",
        "sandbox-runtime",
    )
    blocks = {name: hcl_block(app, f"{name} = {{") for name in service_names}

    for name, block in blocks.items():
        if name == "model-gateway":
            continue
        forbid_markers(
            block,
            PROVIDER_SECRET_MARKERS,
            f"{environment} {name} provider secret boundary",
        )
        require(
            'local.secret_arns["providers/model"]' not in block
            and 'local.secret_arns["providers/media"]' not in block,
            f"{environment} {name} references Provider secret ARNs",
        )

    gateway = blocks["model-gateway"]
    require_hcl_assignment(
        gateway,
        "LUMI_MODEL_PROVIDER_SECRET",
        'local.secret_arns["providers/model"]',
        f"{environment}: Model Gateway must own model Provider secret",
    )
    require_hcl_assignment(
        gateway,
        "LUMI_MEDIA_PROVIDER_SECRET",
        'local.secret_arns["providers/media"]',
        f"{environment}: Model Gateway must own media Provider secret",
    )
    require_hcl_assignment(
        gateway,
        "LUMI_MODEL_GATEWAY_AUTH_SECRET",
        'local.secret_arns["internal/model-gateway"]',
        f"{environment}: Model Gateway internal auth secret missing",
    )
    require(
        "local.model_gateway_environment" not in gateway,
        f"{environment}: Model Gateway must not route back through its own client URL",
    )

    for name in ("agent-runtime", "worker-media"):
        block = blocks[name]
        require(
            "local.model_gateway_environment" in block,
            f"{environment}: {name} must receive the private Model Gateway URL",
        )
        require_hcl_assignment(
            block,
            "LUMI_MODEL_GATEWAY_AUTH_SECRET",
            'local.secret_arns["internal/model-gateway"]',
            f"{environment}: {name} must receive Model Gateway HMAC auth secret",
        )


def validate_ecs_secret_materialization() -> None:
    compute = read(COMPUTE)
    require_markers(
        compute,
        (
            "services_with_secrets = {",
            "for name, service in var.services : name => service "
            "if length(service.secret_arns) > 0",
            'sid       = "ReadDeclaredSecrets"',
            "resources = values(each.value.secret_arns)",
            "for key, arn in each.value.secret_arns",
            "name      = key",
            "valueFrom = arn",
        ),
        "ECS declared-secret materialization",
    )
    require(
        compute.count("resources = values(each.value.secret_arns)") == 1,
        "ECS execution role must authorize exactly the service-declared secret set",
    )


def validate_secret_source_ownership() -> None:
    architecture = read(ARCHITECTURE_CONTRACT)
    require_markers(
        architecture,
        (
            "PROVIDER_SECRET_ENV_NAMES = {",
            '"LUMI_MODEL_PROVIDER_SECRET"',
            '"LUMI_MEDIA_PROVIDER_SECRET"',
            "MODEL_GATEWAY_HOST_SECRET_FILES = {",
            'ROOT / "apps/api/src/lumi_api/model_gateway_service.py"',
            "if path not in MODEL_GATEWAY_HOST_SECRET_FILES:",
            "composite Provider secret is outside Hosted Model Gateway",
        ),
        "Provider secret source ownership scanner",
    )
    require(
        architecture.find("if path not in MODEL_GATEWAY_HOST_SECRET_FILES:")
        < architecture.find("composite Provider secret is outside Hosted Model Gateway"),
        "Provider secret ownership scanner must guard the rejection behind "
        "the exact Hosted host allowlist",
    )


def validate_private_clients() -> None:
    agent = read(AGENT_CLIENT)
    factory = read(AGENT_FACTORY)
    image = read(IMAGE_CLIENT)
    video = read(VIDEO_CLIENT)

    require_markers(
        agent,
        (
            "class HttpProfileModelProvider(ProfileModelProvider)",
            "HttpModelGatewayClient",
            "LUMI_MODEL_GATEWAY_URL",
            "LUMI_MODEL_GATEWAY_AUTH_SECRET",
            "caller_service=_DEFAULT_CALLER_SERVICE",
        ),
        "Agent Runtime private Model Gateway client",
    )
    require_markers(
        factory,
        (
            "class HostedDeepAgentRuntimeFactory(BoundedDeepAgentRuntimeFactory)",
            "models=HttpProfileModelProvider.from_env()",
        ),
        "Agent Runtime hosted composition",
    )
    require_markers(
        image,
        (
            "class HostedImageModelGatewayAdapter",
            'base_url = _required_env("LUMI_MODEL_GATEWAY_URL"',
            'auth_secret = _required_env("LUMI_MODEL_GATEWAY_AUTH_SECRET"',
            'caller_service="worker-media"',
            "HttpModelGatewayEstimateClient",
        ),
        "Worker Media image private Model Gateway client",
    )
    require_markers(
        video,
        (
            "class HostedVideoGateway",
            'base_url = os.getenv("LUMI_MODEL_GATEWAY_URL", "")',
            'auth_secret = os.getenv("LUMI_MODEL_GATEWAY_AUTH_SECRET", "")',
            'caller_service="worker-media"',
            "HttpModelGatewayAsyncClient",
        ),
        "Worker Media video private Model Gateway client",
    )

    for label, source in (
        ("Agent Runtime private client", agent),
        ("Worker Media image private client", image),
        ("Worker Media video private client", video),
    ):
        forbid_markers(source, PROVIDER_SECRET_MARKERS, label)
        forbid_markers(source, RAW_PROVIDER_CREDENTIAL_MARKERS, label)

    gateway = read(GATEWAY_SERVICE)
    require_markers(
        gateway,
        (
            '_ALLOWED_CALLERS = frozenset({"agent-runtime", "worker-media"})',
            '_required_env("LUMI_MODEL_GATEWAY_AUTH_SECRET"',
            '_required_env("LUMI_MODEL_PROVIDER_SECRET"',
            '"LUMI_MEDIA_PROVIDER_SECRET"',
            "verify_internal_request(",
            "allowed_services=_ALLOWED_CALLERS",
        ),
        "Hosted Model Gateway service boundary",
    )


def validate_runtime_provenance() -> None:
    try:
        manifest = json.loads(read(RUNTIME_MANIFEST))
    except json.JSONDecodeError as exc:
        raise ContractError("runtime image manifest is invalid JSON") from exc
    runtimes = manifest.get("runtimes")
    require(isinstance(runtimes, dict), "runtime image manifest missing runtimes")

    expected = {
        "agent-runtime": {
            "apps/agent-runtime/src/lumi_agent_runtime/deep_runtime",
        },
        "worker-media": {
            IMAGE_CLIENT,
            VIDEO_CLIENT,
        },
        "model-gateway": {
            "services/model-gateway",
            "apps/api/src/lumi_api/model_gateway_runtime.py",
            "apps/api/src/lumi_api/model_gateway_bootstrap.py",
            GATEWAY_SERVICE,
            "apps/api/src/lumi_api/model_gateway_cli.py",
        },
    }
    for runtime_name, required_paths in expected.items():
        runtime = runtimes.get(runtime_name) if isinstance(runtimes, dict) else None
        require(isinstance(runtime, dict), f"runtime image manifest missing {runtime_name}")
        sources = set(runtime.get("source_paths") or [])
        missing = required_paths - sources
        require(
            not missing,
            f"runtime image manifest {runtime_name} provenance missing {sorted(missing)}",
        )


def validate_workflow_binding() -> None:
    workflows = (
        (MODEL_WORKFLOW, 3, "Model Gateway workflow"),
        (IAC_WORKFLOW, 2, "Production IaC workflow"),
        (STAGING_WORKFLOW, 2, "Staging Acceptance workflow"),
        (FINAL_WORKFLOW, 2, "Final Acceptance workflow"),
    )
    for path, minimum_count, label in workflows:
        source = read(path)
        require(
            source.count(SELF_PATH) >= minimum_count,
            f"{label} must execute and syntax-gate private Model Gateway deployment contract",
        )
    model_workflow = read(MODEL_WORKFLOW)
    for path in (
        STAGING_APP,
        PRODUCTION_APP,
        COMPUTE,
        AGENT_CLIENT,
        AGENT_FACTORY,
        IMAGE_CLIENT,
        VIDEO_CLIENT,
        GATEWAY_SERVICE,
        RUNTIME_MANIFEST,
        ARCHITECTURE_CONTRACT,
        SELF_PATH,
    ):
        require(
            f'- "{path}"' in model_workflow,
            f"Model Gateway workflow path filter missing {path}",
        )


def main() -> int:
    validate_environment(STAGING_APP, environment="staging")
    validate_environment(PRODUCTION_APP, environment="production")
    validate_ecs_secret_materialization()
    validate_secret_source_ownership()
    validate_private_clients()
    validate_runtime_provenance()
    validate_workflow_binding()
    print(
        "private Model Gateway deployment binding contract: PASS "
        "(IaC secrets -> ECS injection -> Agent/Worker private clients -> runtime provenance)"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        raise SystemExit(f"private Model Gateway deployment contract failed: {exc}") from exc
