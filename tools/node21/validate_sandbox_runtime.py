from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "services/sandbox-runtime/src/lumi_sandbox_runtime"
DOCKERFILE = ROOT / "services/sandbox-runtime/docker/Dockerfile"
PYPROJECT = ROOT / "services/sandbox-runtime/pyproject.toml"
GAPS = ROOT / "reports/nodes/NODE-21/gap-ledger.json"
DOCKER_TEST = ROOT / "tools/node21/test_docker_sandbox.py"
DEEPAGENTS_TEST = ROOT / "tools/node21/test_deepagents_adapter.py"

EXPECTED_GAPS = {
    "SANDBOX-PACKAGE-001",
    "SANDBOX-EGRESS-002",
    "SANDBOX-STORAGE-003",
    "SANDBOX-REMOTE-004",
    "SANDBOX-AUDIT-005",
    "SANDBOX-IMAGE-006",
    "SANDBOX-CI-007",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def validate_no_shell_execution() -> None:
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
                    if keyword.value.value is True:
                        fail(f"shell=True is forbidden in sandbox runtime: {path}")
    source = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py"))
    if "LocalShellBackend" in source:
        fail("Deep Agents LocalShellBackend must not be used by LUMI sandbox runtime")


def validate_docker_hardening() -> None:
    source = (PACKAGE / "docker_backend.py").read_text(encoding="utf-8")
    required = (
        '"--network",\n        "none"',
        '"--read-only"',
        '"--cap-drop"',
        '"ALL"',
        '"no-new-privileges:true"',
        '"--pids-limit"',
        '"--cpus"',
        '"--memory"',
        '"--memory-swap"',
        '"/workspace/input,readonly"',
        '"/workspace/work:rw,nosuid,nodev,size=',
        '"/workspace/output:rw,nosuid,nodev,size=',
        '"--user"',
        "65532:65532",
    )
    missing = [marker for marker in required if marker not in source]
    if missing:
        fail(f"Docker hardening markers missing: {missing}")
    if "/var/run/docker.sock" in source:
        fail("Docker socket mount/reference is forbidden in runtime backend")
    if "create_subprocess_shell" in source:
        fail("create_subprocess_shell is forbidden")


def validate_workspace_helper() -> None:
    helper = (PACKAGE / "workspace_helper.py").read_text(encoding="utf-8")
    for marker in ("os.O_NOFOLLOW", "dir_fd=", "follow_symlinks=False", "stat.S_ISREG"):
        if marker not in helper:
            fail(f"trusted workspace helper missing {marker}")
    workspace = (PACKAGE / "workspace.py").read_text(encoding="utf-8")
    for marker in ("zipfile.ZipFile", "tarfile.open", 'part == ".."'):
        if marker not in workspace:
            fail(f"archive/path validator missing {marker}")


def validate_network_and_secret_policy() -> None:
    policy = (PACKAGE / "policy.py").read_text(encoding="utf-8")
    for marker in (
        "169.254.0.0/16",
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "metadata.google.internal",
        "host.docker.internal",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DATABASE_URL",
        "DOCKER_HOST",
        "real egress enforcement adapter",
    ):
        if marker not in policy:
            fail(f"sandbox network/secret policy missing {marker}")


def validate_deepagents_boundary() -> None:
    adapter = (PACKAGE / "deepagents_adapter.py").read_text(encoding="utf-8")
    for marker in (
        "SandboxBackendProtocol",
        "parse_deepagents_command",
        "punctuation_chars=\"|&;><()\"",
        "SandboxCommand(argv=argv",
        "self._runtime.read_file",
        "self._runtime.write_file",
    ):
        if marker not in adapter:
            fail(f"Deep Agents adapter missing {marker}")
    if "subprocess" in adapter or "os.system" in adapter:
        fail("Deep Agents adapter must not invoke host processes")


def validate_packaging_gap() -> None:
    project = PYPROJECT.read_text(encoding="utf-8")
    if "dependencies = []" not in project:
        fail("sandbox pyproject changed without a corresponding frozen uv.lock update")
    ledger = json.loads(GAPS.read_text(encoding="utf-8"))
    ids = {item["id"] for item in ledger["gaps"]}
    if ids != EXPECTED_GAPS:
        fail(f"unexpected NODE-21 gaps: {sorted(ids)}")


def validate_attack_evidence() -> None:
    docker_test = DOCKER_TEST.read_text(encoding="utf-8")
    markers = (
        "169.254.169.254",
        "/var/run/docker.sock",
        "symlink",
        "zip-slip",
        "pids_limit",
        "memory_limit_mb=128",
        "disk_limit_mb=64",
        "timed_out is True",
        "output_truncated is True",
        "ffprobe",
        "convert",
    )
    missing = [marker for marker in markers if marker not in docker_test]
    if missing:
        fail(f"Docker attack/functional evidence missing: {missing}")
    deepagents = DEEPAGENTS_TEST.read_text(encoding="utf-8")
    if "issubclass(DeepAgentsSandboxAdapter, SandboxBackendProtocol)" not in deepagents:
        fail("Deep Agents protocol compatibility assertion missing")


def validate_image() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    for marker in (
        "python:3.12-slim-bookworm",
        "ffmpeg",
        "imagemagick",
        "nodejs",
        "fontconfig",
        "USER 65532:65532",
        "/opt/lumi/workspace_helper.py",
    ):
        if marker not in dockerfile:
            fail(f"sandbox image missing {marker}")
    forbidden = ("awscli", "azure-cli", "google-cloud-cli", "docker-ce", "kubectl")
    for marker in forbidden:
        if marker in dockerfile:
            fail(f"cloud/host administration tool forbidden in sandbox image: {marker}")


def main() -> None:
    validate_no_shell_execution()
    validate_docker_hardening()
    validate_workspace_helper()
    validate_network_and_secret_policy()
    validate_deepagents_boundary()
    validate_packaging_gap()
    validate_attack_evidence()
    validate_image()
    print("NODE21_SANDBOX_SECURITY_CONTRACT_VALID")


if __name__ == "__main__":
    main()
