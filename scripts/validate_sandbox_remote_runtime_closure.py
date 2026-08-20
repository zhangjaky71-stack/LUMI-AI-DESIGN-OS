#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ClosureError(RuntimeError):
    pass


def _read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise ClosureError(f"required sandbox closure source is missing: {relative}")
    return path.read_text(encoding="utf-8")


def _require(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    if missing:
        raise ClosureError(f"{label} missing required markers: {missing}")


def _forbid(source: str, markers: tuple[str, ...], label: str) -> None:
    present = [marker for marker in markers if marker in source]
    if present:
        raise ClosureError(f"{label} contains forbidden markers: {present}")


def validate() -> None:
    cli = _read("services/sandbox-runtime/src/lumi_sandbox_runtime/cli.py")
    hosted = _read("services/sandbox-runtime/src/lumi_sandbox_runtime/hosted_service.py")
    discovery = _read("services/sandbox-runtime/src/lumi_sandbox_runtime/ecs_discovery.py")
    backend = _read("services/sandbox-runtime/src/lumi_sandbox_runtime/ecs_backend.py")
    child = _read("services/sandbox-runtime/src/lumi_sandbox_runtime/child_cli.py")
    pyproject = _read("services/sandbox-runtime/pyproject.toml")
    dockerfile = _read("services/sandbox-runtime/Dockerfile")
    terraform = _read("infra/iac/modules/compute/sandbox_child.tf")
    endpoint = _read("infra/iac/modules/network/sandbox_ecs_endpoint.tf")

    _require(
        cli,
        ("lumi_sandbox_runtime.hosted_service:create_runtime_app",),
        "sandbox production CLI",
    )
    _require(
        hosted,
        ("discover_remote_backend()", "HostedSandboxRuntime", "backend=discover_remote_backend()"),
        "sandbox hosted composition",
    )
    _forbid(
        hosted,
        ("LocalBackend", "DockerBackend", "subprocess", "docker.sock"),
        "sandbox hosted composition",
    )
    _require(
        discovery,
        (
            "ECS_CONTAINER_METADATA_URI_V4",
            'services=["sandbox-runtime"]',
            'awsvpc.get("assignPublicIp") != "DISABLED"',
            'child_family = f"lumi-{environment}-sandbox-child"',
            'container="sandbox-child"',
        ),
        "sandbox ECS discovery",
    )
    _require(
        backend,
        (
            'launchType="FARGATE"',
            '"assignPublicIp": "DISABLED"',
            '"LUMI_SANDBOX_REQUEST_KEY"',
            '"LUMI_SANDBOX_RESULT_KEY"',
            'f"sandbox-log://{sandbox_id}/{operation_id}"',
            '"sandbox-exchange/v1/',
        ),
        "sandbox remote backend",
    )
    _forbid(
        backend,
        ("subprocess.run", "subprocess.Popen", "DockerBackend", "/var/run/docker.sock"),
        "sandbox remote backend",
    )
    _require(
        child,
        (
            "subprocess.run(",
            "stdin=subprocess.DEVNULL",
            '"HOME": str(work)',
            '"TMPDIR": str(work)',
            'prefix = "sandbox-exchange/v1/"',
        ),
        "sandbox isolated child",
    )
    _require(
        pyproject,
        (
            '"boto3>=1.42,<2"',
            'lumi-sandbox-child = "lumi_sandbox_runtime.child_cli:main"',
        ),
        "sandbox package",
    )
    _require(
        dockerfile,
        (
            "uv sync --all-packages --frozen --no-dev",
            "USER 10001:10001",
            'CMD ["lumi-sandbox-runtime"]',
        ),
        "sandbox image",
    )
    _require(
        terraform,
        (
            'family                   = "${local.name}-sandbox-child"',
            'name      = "sandbox-child"',
            'command   = ["lumi-sandbox-child"]',
            "readonlyRootFilesystem = true",
            'containerPath = "/tmp"',
            'CustomerSecrets  = "none"',
            '"ecs:RunTask"',
            '"iam:PassRole"',
            '"ecs:DescribeServices"',
            '"${local.sandbox_bucket_arn}/sandbox-exchange/v1/*"',
        ),
        "sandbox child Terraform",
    )
    _forbid(
        terraform,
        (
            "secret_arns",
            "secrets =",
            "0.0.0.0/0",
            "providers/model",
            "auth/signing",
            "database/app",
        ),
        "sandbox child Terraform",
    )
    _require(
        endpoint,
        (
            'service_name        = "com.amazonaws.${data.aws_region.current.name}.ecs"',
            "private_dns_enabled = true",
            "aws_security_group.runtime_endpoints.id",
        ),
        "sandbox ECS PrivateLink",
    )


def self_test() -> None:
    good = 'launchType="FARGATE"\n"assignPublicIp": "DISABLED"'
    _require(good, ('launchType="FARGATE"', '"assignPublicIp": "DISABLED"'), "self-test")
    try:
        _forbid("subprocess.run", ("subprocess.run",), "self-test")
    except ClosureError:
        return
    raise RuntimeError("sandbox closure self-test failed to reject host subprocess")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            validate()
    except ClosureError as exc:
        raise SystemExit(f"Sandbox remote runtime closure: BLOCKED: {exc}") from exc
    print("Sandbox remote runtime closure: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
