from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

from lumi_sandbox_runtime import (
    DeepAgentSandboxTools,
    DockerSandboxBackend,
    ExecRequest,
    JsonlAuditSink,
    ResolvedAsset,
    SandboxError,
    SandboxPathError,
    SandboxPolicyError,
    SandboxReaper,
    SandboxSpec,
    SandboxState,
    SandboxTimeoutError,
)

RUNTIME_ROOT = Path(os.getenv("LUMI_SANDBOX_RUNTIME_ROOT", "/tmp/lumi-node21-e2e"))
IMAGE = os.getenv("LUMI_SANDBOX_IMAGE", "lumi-sandbox:node21-v1")
HOST_PRIVATE_MARKER_NAME = "LUMI_NODE21_HOST_PRIVATE_MARKER"
HOST_PRIVATE_MARKER_VALUE = "node21-" + "host-only-marker"
_MIB = 1024 * 1024


class AssetResolver:
    def resolve(self, asset_ref: str) -> ResolvedAsset:
        payload = f"asset payload for {asset_ref}\n".encode()
        return ResolvedAsset(
            asset_ref=asset_ref,
            filename="input note.txt",
            data=payload,
            checksum_sha256=hashlib.sha256(payload).hexdigest(),
        )


class SizedAssetResolver:
    def resolve(self, asset_ref: str) -> ResolvedAsset:
        fill = b"a" if asset_ref.endswith("a") else b"b"
        payload = fill * (20 * _MIB)
        return ResolvedAsset(
            asset_ref=asset_ref,
            filename=f"{asset_ref.rsplit(':', 1)[-1]}.bin",
            data=payload,
            checksum_sha256=hashlib.sha256(payload).hexdigest(),
        )


class ArtifactSink:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def store_file(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        sandbox_id: UUID,
        filename: str,
        source: Path,
        checksum_sha256: str,
        detected_mime: str,
    ) -> str:
        del organization_id, agent_run_id, detected_mime
        target = self.root / f"{sandbox_id}-{filename}"
        shutil.copy2(source, target)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        assert actual == checksum_sha256
        return f"asset://node21/{target.name}"


def sandbox_spec(
    *,
    memory_limit_mb: int = 256,
    disk_limit_mb: int = 128,
    pids_limit: int = 64,
    timeout_seconds: int = 10,
    max_output_bytes: int = 4096,
    ttl_seconds: int = 120,
) -> SandboxSpec:
    return SandboxSpec(
        organization_id=uuid4(),
        agent_run_id=uuid4(),
        image=IMAGE,
        cpu_limit=1.0,
        memory_limit_mb=memory_limit_mb,
        disk_limit_mb=disk_limit_mb,
        pids_limit=pids_limit,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
        ttl_seconds=ttl_seconds,
    )


def make_backend() -> DockerSandboxBackend:
    return DockerSandboxBackend(
        runtime_root=RUNTIME_ROOT,
        audit_sink=JsonlAuditSink(RUNTIME_ROOT / "audit" / "sandbox.jsonl"),
        asset_resolver=AssetResolver(),
        artifact_sink=ArtifactSink(RUNTIME_ROOT / "collected"),
    )


def functional_and_boundary_test(backend: DockerSandboxBackend) -> None:
    os.environ[HOST_PRIVATE_MARKER_NAME] = HOST_PRIVATE_MARKER_VALUE
    sandbox_id = backend.create(sandbox_spec())
    try:
        tools = DeepAgentSandboxTools(backend, sandbox_id)
        python_result = tools.execute(["python", "-c", "print('python-ok')"])
        assert python_result["exit_code"] == 0
        assert python_result["stdout"].strip() == "python-ok"

        node_result = tools.execute(["node", "-e", "console.log('node-ok')"])
        assert node_result["exit_code"] == 0
        assert node_result["stdout"].strip() == "node-ok"

        ffmpeg_result = tools.execute(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=16x16:d=0.2",
                "-c:v",
                "mpeg4",
                "-y",
                "/workspace/output/sample.mp4",
            ],
            timeout=10,
        )
        assert ffmpeg_result["exit_code"] == 0, ffmpeg_result
        probe_result = tools.execute(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                "/workspace/output/sample.mp4",
            ]
        )
        assert probe_result["exit_code"] == 0
        assert float(probe_result["stdout"].strip()) > 0

        image_result = tools.execute(
            [
                "convert",
                "-size",
                "8x8",
                "xc:white",
                "/workspace/output/pixel.png",
            ]
        )
        assert image_result["exit_code"] == 0, image_result

        input_path = tools.upload_asset("asset:node21-input")
        assert input_path.startswith("input/")
        assert b"node21-input" in tools.read_file(input_path)

        tools.write_file("work/nested/note.txt", b"sandbox file tool\n")
        assert tools.read_file("work/nested/note.txt") == b"sandbox file tool\n"
        append_result = tools.execute(
            [
                "python",
                "-c",
                "p='/workspace/work/nested/note.txt'; "
                "open(p, 'ab').write(b'container-user-write\\n')",
            ]
        )
        assert append_result["exit_code"] == 0, append_result
        note = tools.read_file("work/nested/note.txt")
        assert note.endswith(b"container-user-write\n")
        entries = tools.list_files("work/nested")
        assert any(entry["path"].endswith("note.txt") for entry in entries)

        symlink = tools.execute(
            ["ln", "-s", "/etc/passwd", "/workspace/work/escape"]
        )
        assert symlink["exit_code"] == 0
        try:
            tools.read_file("work/escape")
        except SandboxPolicyError:
            pass
        else:
            raise AssertionError("symlink escape must be rejected")

        try:
            tools.read_file("../../etc/passwd")
        except SandboxPathError:
            pass
        else:
            raise AssertionError("path traversal must be rejected")

        private_marker = tools.execute(
            [
                "python",
                "-c",
                f"import os; print({HOST_PRIVATE_MARKER_NAME!r} in os.environ)",
            ]
        )
        assert private_marker["stdout"].strip() == "False"

        socket_check = tools.execute(
            [
                "python",
                "-c",
                "import os; p='/'+'var'+'/run/'+'docker.sock'; print(os.path.exists(p))",
            ]
        )
        assert socket_check["stdout"].strip() == "False"

        metadata = tools.execute(
            [
                "python",
                "-c",
                "import socket; s=socket.socket(); s.settimeout(1); "
                "print(s.connect_ex(('169.254.169.254', 80)))",
            ],
            timeout=3,
        )
        assert metadata["stdout"].strip() != "0"

        flood = tools.execute(["python", "-c", "print('x' * 200000)"])
        assert flood["stdout_truncated"] is True
        assert len(flood["stdout"].encode()) <= 4096
        staging = RUNTIME_ROOT / str(sandbox_id) / "staging"
        assert not tuple(staging.glob("exec-*"))

        artifact = tools.collect_artifact("output/pixel.png")
        assert artifact["detected_mime"] == "image/png"
        assert artifact["storage_ref"].startswith("asset://node21/")
        assert len(artifact["checksum_sha256"]) == 64

        audit_path = RUNTIME_ROOT / "audit" / "sandbox.jsonl"
        audit_text = audit_path.read_text(encoding="utf-8")
        assert HOST_PRIVATE_MARKER_VALUE not in audit_text
        assert "sandbox.exec.completed" in audit_text
        assert "sandbox.artifact.collected" in audit_text
    finally:
        backend.terminate(sandbox_id)
    assert backend.state(sandbox_id) == SandboxState.TERMINATED
    assert not (RUNTIME_ROOT / str(sandbox_id)).exists()
    containers = subprocess.run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=lumi.sandbox.id={sandbox_id}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert not containers.stdout.strip()


def input_quota_test() -> None:
    backend = DockerSandboxBackend(
        runtime_root=RUNTIME_ROOT,
        audit_sink=JsonlAuditSink(RUNTIME_ROOT / "audit" / "sandbox.jsonl"),
        asset_resolver=SizedAssetResolver(),
    )
    sandbox_id = backend.create(sandbox_spec(disk_limit_mb=32))
    try:
        first = backend.upload_asset(sandbox_id, "asset:large-a")
        assert first.startswith("input/")
        try:
            backend.upload_asset(sandbox_id, "asset:large-b")
        except SandboxPolicyError as exc:
            assert "INPUT_QUOTA_EXCEEDED" in str(exc)
        else:
            raise AssertionError("cumulative input quota must reject the second asset")
    finally:
        backend.terminate(sandbox_id)


def timeout_test(backend: DockerSandboxBackend) -> None:
    sandbox_id = backend.create(sandbox_spec(timeout_seconds=2))
    try:
        try:
            backend.exec(
                sandbox_id,
                ExecRequest(("sleep", "30"), timeout_seconds=1),
            )
        except SandboxTimeoutError:
            pass
        else:
            raise AssertionError("long command must time out")
        assert backend.state(sandbox_id) == SandboxState.FAILED
    finally:
        backend.terminate(sandbox_id)


def active_ttl_test(backend: DockerSandboxBackend) -> None:
    sandbox_id = backend.create(sandbox_spec(timeout_seconds=30, ttl_seconds=5))
    started = time.monotonic()
    try:
        try:
            backend.exec(
                sandbox_id,
                ExecRequest(("sleep", "30"), timeout_seconds=30),
            )
        except SandboxTimeoutError:
            pass
        else:
            raise AssertionError("running command must not cross sandbox TTL")
        assert time.monotonic() - started < 10
    finally:
        backend.terminate(sandbox_id)


def pid_limit_test(backend: DockerSandboxBackend) -> None:
    sandbox_id = backend.create(sandbox_spec(pids_limit=16))
    code = """
import subprocess
procs = []
try:
    for _ in range(100):
        try:
            procs.append(subprocess.Popen(["sleep", "2"]))
        except OSError:
            break
    print(len(procs))
finally:
    for proc in procs:
        proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
""".strip()
    try:
        result = backend.exec(
            sandbox_id,
            ExecRequest(("python", "-c", code), timeout_seconds=8),
        )
        assert result.exit_code == 0, result
        assert int(result.stdout.strip()) < 100
    finally:
        backend.terminate(sandbox_id)


def memory_limit_test(backend: DockerSandboxBackend) -> None:
    sandbox_id = backend.create(sandbox_spec(memory_limit_mb=96))
    try:
        try:
            result = backend.exec(
                sandbox_id,
                ExecRequest(
                    (
                        "python",
                        "-c",
                        "x=bytearray(512*1024*1024); print(len(x))",
                    ),
                    timeout_seconds=8,
                ),
            )
        except SandboxError:
            return
        assert result.exit_code != 0
    finally:
        backend.terminate(sandbox_id)


def disk_limit_test(backend: DockerSandboxBackend) -> None:
    sandbox_id = backend.create(sandbox_spec(disk_limit_mb=32))
    code = """
try:
    with open("/workspace/work/fill.bin", "wb") as handle:
        for _ in range(64):
            handle.write(b"x" * 1024 * 1024)
except OSError as exc:
    print(exc.errno)
    raise SystemExit(23)
raise SystemExit(0)
""".strip()
    try:
        result = backend.exec(
            sandbox_id,
            ExecRequest(("python", "-c", code), timeout_seconds=8),
        )
        assert result.exit_code == 23, result
    finally:
        backend.terminate(sandbox_id)


def ttl_reaper_test(backend: DockerSandboxBackend) -> None:
    sandbox_id = backend.create(sandbox_spec(ttl_seconds=5))
    with SandboxReaper(backend, interval_seconds=0.25):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if backend.state(sandbox_id) == SandboxState.TERMINATED:
                break
            time.sleep(0.1)
    assert backend.state(sandbox_id) == SandboxState.TERMINATED


def main() -> int:
    if os.getenv("LUMI_SANDBOX_DOCKER_E2E") != "1":
        print("NODE-21 Docker E2E: SKIPPED (set LUMI_SANDBOX_DOCKER_E2E=1)")
        return 0
    shutil.rmtree(RUNTIME_ROOT, ignore_errors=True)
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    backend = make_backend()
    backend.reap_orphaned_containers()
    functional_and_boundary_test(backend)
    input_quota_test()
    timeout_test(backend)
    active_ttl_test(backend)
    pid_limit_test(backend)
    memory_limit_test(backend)
    disk_limit_test(backend)
    ttl_reaper_test(backend)
    backend.reap_orphaned_containers()
    print("NODE-21 sandbox runtime Docker/security integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
