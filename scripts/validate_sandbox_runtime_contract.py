from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-21 contract marker: {needle}")


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden NODE-21 marker: {needle}")


def assert_agent_adapter_has_no_host_exec() -> None:
    path = ROOT / "services/sandbox-runtime/src/lumi_sandbox_runtime/deep_agents.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = {"subprocess", "os", "docker", "shlex"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name.split(".", 1)[0] for alias in node.names}
            if names & forbidden:
                raise SystemExit("Deep Agent sandbox adapter imports host execution modules")
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".", 1)[0] in forbidden:
                raise SystemExit("Deep Agent sandbox adapter imports host execution modules")


def main() -> int:
    backend = "services/sandbox-runtime/src/lumi_sandbox_runtime/local_backend.py"
    public_backend = "services/sandbox-runtime/src/lumi_sandbox_runtime/docker_backend.py"
    require(
        "services/sandbox-runtime/src/lumi_sandbox_runtime/models.py",
        'NONE = "NONE"',
        'TOOL_PROXY_ONLY = "TOOL_PROXY_ONLY"',
        'ALLOWLIST = "ALLOWLIST"',
        'FAILED = "FAILED"',
        "max_output_bytes",
        "pids_limit",
        "SANDBOX_OUTPUT_BUDGET_EXCEEDS_STORAGE",
    )
    require(
        backend,
        '"--network",\n            "none"',
        '"--read-only"',
        '"--cap-drop",\n            "ALL"',
        '"no-new-privileges:true"',
        '"--pids-limit"',
        '"--memory"',
        '"--cpus"',
        '"--tmpfs"',
        "uid={uid},gid={gid},mode=0700",
        "shell=False",
        "JsonlAuditSink",
        "SANDBOX_DIRECTORY_TOO_LARGE",
        "SANDBOX_WRITE_TOO_LARGE",
        "SANDBOX_STRAY_PROCESS_DETECTED",
        "SANDBOX_EXEC_TIMEOUT",
    )
    require(
        public_backend,
        "SANDBOX_ROOT_HOST_EXECUTION_FORBIDDEN",
        "remaining_seconds",
        "requested_timeout",
        '"exec",\n                        "-i"',
        "SANDBOX_INPUT_QUOTA_EXCEEDED",
        "SANDBOX_WRITE_TIMEOUT",
        "_cleanup_exec_staging",
        "_prune_oldest_files",
        "_best_effort_kill",
        "record.expires_monotonic <= now",
        "shell=False",
    )
    forbid(
        backend,
        "shell=True",
        "--privileged",
        "--env-file",
        "type=bind,src=/var/run/docker.sock",
    )
    forbid(
        public_backend,
        "shell=True",
        "--privileged",
        "--env-file",
    )
    require(
        "services/sandbox-runtime/src/lumi_sandbox_runtime/audit.py",
        "max_bytes",
        "_rotate_if_needed",
        "os.replace",
    )
    require(
        "services/sandbox-runtime/src/lumi_sandbox_runtime/security.py",
        "SANDBOX_PATH_TRAVERSAL",
        "SANDBOX_ARCHIVE_SYMLINK_FORBIDDEN",
        "169.254.",
        "metadata.google.internal",
        "<redacted>",
    )
    require(
        "infra/sandbox/Dockerfile",
        "USER 65532:65532",
        "ffmpeg",
        "imagemagick",
        "nodejs",
        "fontconfig",
    )
    assert_agent_adapter_has_no_host_exec()
    print("NODE-21 sandbox runtime static security contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
