from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .backend import ArtifactStoragePort
from .models import (
    AssetInputRef,
    CollectedArtifact,
    ExecResult,
    FileEntry,
    ResourceUsage,
    SandboxCommand,
    SandboxHandle,
    SandboxSpec,
    SandboxState,
)
from .policy import CommandPolicy, SandboxPolicyDenied, validate_network_policy
from .redaction import SecretRedactor
from .workspace import normalize_workspace_path, validate_archive_bytes

_HELPER = "/opt/lumi/workspace_helper.py"
_SANDBOX_USER = "65532:65532"


class SandboxNotFound(KeyError):
    code = "SANDBOX_NOT_FOUND"


class SandboxRuntimeError(RuntimeError):
    code = "SANDBOX_RUNTIME_ERROR"


@dataclass(slots=True)
class _Session:
    handle: SandboxHandle
    spec: SandboxSpec
    container_name: str
    root_dir: Path
    input_dir: Path
    state: SandboxState = SandboxState.READY
    input_bytes: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    expiry_task: asyncio.Task[None] | None = None


def build_docker_run_args(
    spec: SandboxSpec,
    *,
    container_name: str,
    input_dir: Path,
) -> tuple[str, ...]:
    if spec.network_policy.value != "none":
        raise SandboxPolicyDenied(
            "local Docker backend only supports enforced network NONE"
        )
    work_mb = max(32, int(spec.disk_limit_mb * 0.7))
    output_mb = max(16, spec.disk_limit_mb - work_mb)
    memory = f"{spec.memory_limit_mb}m"
    return (
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        container_name,
        "--label",
        "lumi.sandbox=true",
        "--label",
        f"lumi.organization_id={spec.organization_id}",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(spec.pids_limit),
        "--cpus",
        str(spec.cpu_limit),
        "--memory",
        memory,
        "--memory-swap",
        memory,
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--tmpfs",
        (
            f"/workspace/work:rw,nosuid,nodev,size={work_mb}m,"
            "uid=65532,gid=65532,mode=0700"
        ),
        "--tmpfs",
        (
            f"/workspace/output:rw,nosuid,nodev,size={output_mb}m,"
            "uid=65532,gid=65532,mode=0700"
        ),
        "--mount",
        f"type=bind,src={input_dir},dst=/workspace/input,readonly",
        "--env",
        "HOME=/tmp",
        "--env",
        "LANG=C.UTF-8",
        "--env",
        "LC_ALL=C.UTF-8",
        "--env",
        f"LUMI_SANDBOX_ID={container_name}",
        "--user",
        _SANDBOX_USER,
        spec.image,
        "python",
        "-c",
        "import time; time.sleep(10**9)",
    )


async def _read_limited(
    stream: asyncio.StreamReader | None,
    limit: int,
) -> tuple[bytes, int, bool]:
    if stream is None:
        return b"", 0, False
    kept = bytearray()
    seen = 0
    truncated = False
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        seen += len(chunk)
        remaining = max(0, limit - len(kept))
        if remaining:
            kept.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
    return bytes(kept), seen, truncated


async def _run_process(
    argv: tuple[str, ...],
    *,
    stdin: bytes | None = None,
    timeout: float | None = None,
    max_output_bytes: int = 1_048_576,
) -> tuple[int, bytes, bytes, int, int, bool, bool]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=(
            asyncio.subprocess.PIPE
            if stdin is not None
            else asyncio.subprocess.DEVNULL
        ),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if stdin is not None and process.stdin is not None:
        process.stdin.write(stdin)
        await process.stdin.drain()
        process.stdin.close()
    stdout_limit = max_output_bytes // 2
    stderr_limit = max_output_bytes - stdout_limit
    stdout_task = asyncio.create_task(_read_limited(process.stdout, stdout_limit))
    stderr_task = asyncio.create_task(_read_limited(process.stderr, stderr_limit))
    timed_out = False
    try:
        if timeout is None:
            await process.wait()
        else:
            await asyncio.wait_for(process.wait(), timeout=timeout)
    except TimeoutError:
        timed_out = True
        process.kill()
        await process.wait()
    stdout, stdout_seen, stdout_truncated = await stdout_task
    stderr, stderr_seen, stderr_truncated = await stderr_task
    return (
        int(process.returncode or 0),
        stdout,
        stderr,
        stdout_seen,
        stderr_seen,
        stdout_truncated or stderr_truncated,
        timed_out,
    )


def _base64_transport_budget(raw_bytes: int) -> int:
    encoded = ((raw_bytes + 2) // 3) * 4
    stdout_budget = encoded + 131_072
    return stdout_budget * 2


class DockerSandboxBackend:
    def __init__(
        self,
        *,
        command_policy: CommandPolicy | None = None,
        storage: ArtifactStoragePort | None = None,
        redactor: SecretRedactor | None = None,
        docker_binary: str = "docker",
        egress_enforcer_available: bool = False,
    ) -> None:
        self.command_policy = command_policy or CommandPolicy()
        self.storage = storage
        self.redactor = redactor or SecretRedactor()
        self.docker_binary = docker_binary
        self.egress_enforcer_available = egress_enforcer_available
        self._sessions: dict[str, _Session] = {}
        self._registry_lock = asyncio.Lock()

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        validate_network_policy(
            spec,
            egress_enforcer_available=self.egress_enforcer_available,
        )
        if spec.network_policy.value != "none":
            raise SandboxPolicyDenied(
                "local backend refuses proxy/allowlist mode until a real network enforcer is bound"
            )
        sandbox_id = f"sbx-{uuid4().hex}"
        root = Path(tempfile.mkdtemp(prefix=f"lumi-{sandbox_id}-"))
        input_dir = root / "input"
        input_dir.mkdir(mode=0o755)
        container_name = f"lumi-{sandbox_id}"
        args = list(
            build_docker_run_args(
                spec,
                container_name=container_name,
                input_dir=input_dir,
            )
        )
        args[0] = self.docker_binary
        code, stdout, stderr, *_ = await _run_process(
            tuple(args),
            timeout=60,
            max_output_bytes=65536,
        )
        if code != 0:
            shutil.rmtree(root, ignore_errors=True)
            error = self.redactor.redact(stderr.decode("utf-8", "replace"))
            raise SandboxRuntimeError(f"docker create failed: {error}")
        if not stdout.strip():
            shutil.rmtree(root, ignore_errors=True)
            raise SandboxRuntimeError("docker did not return a container id")
        now = datetime.now(UTC)
        handle = SandboxHandle(
            sandbox_id=sandbox_id,
            organization_id=spec.organization_id,
            agent_run_id=spec.agent_run_id,
            state=SandboxState.READY,
            image_version=spec.image_version,
            created_at=now,
            expires_at=now + timedelta(seconds=spec.ttl_seconds),
        )
        session = _Session(
            handle=handle,
            spec=spec,
            container_name=container_name,
            root_dir=root,
            input_dir=input_dir,
        )
        async with self._registry_lock:
            self._sessions[sandbox_id] = session
        session.expiry_task = asyncio.create_task(
            self._expire(sandbox_id, spec.ttl_seconds)
        )
        return handle

    async def exec(
        self,
        sandbox_id: str,
        command: SandboxCommand,
    ) -> ExecResult:
        session = self._get(sandbox_id)
        self.command_policy.validate(command)
        cwd = normalize_workspace_path(command.cwd)
        timeout = command.timeout_seconds or session.spec.command_timeout_seconds
        async with session.lock:
            self._assert_live(session)
            session.state = SandboxState.RUNNING
            argv: list[str] = [
                self.docker_binary,
                "exec",
                "--user",
                _SANDBOX_USER,
                "--workdir",
                cwd,
            ]
            for key, value in sorted(command.env.items()):
                argv.extend(("--env", f"{key}={value}"))
            argv.append(session.container_name)
            argv.extend(command.argv)
            started = time.monotonic()
            (
                code,
                stdout,
                stderr,
                stdout_seen,
                stderr_seen,
                truncated,
                timed_out,
            ) = await _run_process(
                tuple(argv),
                timeout=timeout,
                max_output_bytes=session.spec.max_output_bytes,
            )
            wall_ms = int((time.monotonic() - started) * 1000)
            if timed_out:
                await self._kill_container(session)
                session.state = SandboxState.FAILED
            else:
                session.state = SandboxState.IDLE
            return ExecResult(
                exit_code=124 if timed_out else code,
                stdout=self.redactor.redact(
                    stdout.decode("utf-8", "replace")
                ),
                stderr=self.redactor.redact(
                    stderr.decode("utf-8", "replace")
                ),
                timed_out=timed_out,
                usage=ResourceUsage(
                    wall_time_ms=wall_ms,
                    stdout_bytes=stdout_seen,
                    stderr_bytes=stderr_seen,
                    output_truncated=truncated,
                ),
            )

    async def read_file(self, sandbox_id: str, path: str) -> bytes:
        session = self._get(sandbox_id)
        normalized = normalize_workspace_path(path)
        async with session.lock:
            self._assert_live(session)
            payload = await self._helper(
                session,
                "read",
                normalized,
                "--max-bytes",
                str(session.spec.max_output_bytes),
                transport_limit=_base64_transport_budget(
                    session.spec.max_output_bytes
                ),
            )
            return base64.b64decode(
                payload.strip().encode("ascii"),
                validate=True,
            )

    async def write_file(
        self,
        sandbox_id: str,
        path: str,
        content: bytes,
    ) -> None:
        session = self._get(sandbox_id)
        normalized = normalize_workspace_path(path)
        if normalized.startswith("/workspace/input/"):
            raise SandboxPolicyDenied("input is read-only")
        async with session.lock:
            self._assert_live(session)
            await self._helper(
                session,
                "write",
                normalized,
                "--max-bytes",
                str(session.spec.disk_limit_mb * 1024 * 1024),
                stdin=base64.b64encode(content) + b"\n",
            )

    async def list_files(
        self,
        sandbox_id: str,
        path: str,
    ) -> list[FileEntry]:
        session = self._get(sandbox_id)
        normalized = normalize_workspace_path(path)
        async with session.lock:
            self._assert_live(session)
            raw = await self._helper(session, "list", normalized)
            data = json.loads(raw)
            return [FileEntry.model_validate(item) for item in data]

    async def upload_asset(
        self,
        sandbox_id: str,
        asset: AssetInputRef,
    ) -> str:
        session = self._get(sandbox_id)
        invalid_name = (
            "/" in asset.filename
            or "\\" in asset.filename
            or asset.filename in {".", ".."}
        )
        if invalid_name:
            raise SandboxPolicyDenied("asset filename must be a basename")
        validate_archive_bytes(asset.filename, asset.content)
        async with session.lock:
            self._assert_live(session)
            next_total = session.input_bytes + len(asset.content)
            if next_total > session.spec.disk_limit_mb * 1024 * 1024:
                raise SandboxPolicyDenied(
                    "input assets exceed sandbox disk budget"
                )
            target = session.input_dir / asset.filename
            if target.exists():
                raise SandboxPolicyDenied("input filename already exists")
            target.write_bytes(asset.content)
            os.chmod(target, 0o444)
            session.input_bytes = next_total
            return f"/workspace/input/{asset.filename}"

    async def collect_artifact(
        self,
        sandbox_id: str,
        path: str,
    ) -> CollectedArtifact:
        session = self._get(sandbox_id)
        normalized = normalize_workspace_path(path)
        if not normalized.startswith("/workspace/output/"):
            raise SandboxPolicyDenied(
                "only /workspace/output files may be collected"
            )
        async with session.lock:
            self._assert_live(session)
            raw = await self._helper(
                session,
                "inspect",
                normalized,
                "--max-bytes",
                str(session.spec.max_artifact_bytes),
                transport_limit=_base64_transport_budget(
                    session.spec.max_artifact_bytes
                ),
            )
            metadata: dict[str, Any] = json.loads(raw)
            content = base64.b64decode(
                metadata.pop("content_b64").encode("ascii"),
                validate=True,
            )
            storage_ref = None
            if self.storage is not None:
                storage_ref = await self.storage.put_validated_output(
                    organization_id=str(session.spec.organization_id),
                    sandbox_id=sandbox_id,
                    path=normalized,
                    content=content,
                    sha256=str(metadata["sha256"]),
                    detected_mime=str(metadata["detected_mime"]),
                )
            return CollectedArtifact(
                sandbox_id=sandbox_id,
                path=normalized,
                sha256=str(metadata["sha256"]),
                size=int(metadata["size"]),
                detected_mime=str(metadata["detected_mime"]),
                storage_ref=storage_ref,
            )

    async def terminate(self, sandbox_id: str) -> None:
        session = self._sessions.get(sandbox_id)
        if session is None:
            return
        async with session.lock:
            if session.state in {
                SandboxState.TERMINATED,
                SandboxState.TERMINATING,
            }:
                return
            session.state = SandboxState.TERMINATING
            await self._kill_container(session)
            session.state = SandboxState.TERMINATED
        current = asyncio.current_task()
        if (
            session.expiry_task is not None
            and session.expiry_task is not current
        ):
            session.expiry_task.cancel()
        shutil.rmtree(session.root_dir, ignore_errors=True)
        async with self._registry_lock:
            self._sessions.pop(sandbox_id, None)

    async def cleanup_stale(self) -> None:
        code, stdout, _, *_ = await _run_process(
            (
                self.docker_binary,
                "ps",
                "-aq",
                "--filter",
                "label=lumi.sandbox=true",
            ),
            timeout=30,
            max_output_bytes=262144,
        )
        if code != 0:
            return
        for container_id in stdout.decode("utf-8", "replace").split():
            await _run_process(
                (self.docker_binary, "rm", "-f", container_id),
                timeout=30,
                max_output_bytes=65536,
            )

    async def _helper(
        self,
        session: _Session,
        *args: str,
        stdin: bytes | None = None,
        transport_limit: int | None = None,
    ) -> str:
        limit = transport_limit or max(
            session.spec.max_output_bytes,
            4_194_304,
        )
        (
            code,
            stdout,
            stderr,
            _stdout_seen,
            _stderr_seen,
            truncated,
            timed_out,
        ) = await _run_process(
            (
                self.docker_binary,
                "exec",
                "--user",
                _SANDBOX_USER,
                session.container_name,
                "python",
                _HELPER,
                *args,
            ),
            stdin=stdin,
            timeout=30,
            max_output_bytes=limit,
        )
        if timed_out:
            raise SandboxRuntimeError("trusted workspace helper timed out")
        if truncated:
            raise SandboxPolicyDenied(
                "trusted workspace helper output exceeded transport limit"
            )
        if code != 0:
            detail = self.redactor.redact(
                stderr.decode("utf-8", "replace")
            ).strip()
            raise SandboxPolicyDenied(
                detail or "trusted workspace helper rejected operation"
            )
        return stdout.decode("utf-8", "strict")

    async def _kill_container(self, session: _Session) -> None:
        await _run_process(
            (
                self.docker_binary,
                "rm",
                "-f",
                session.container_name,
            ),
            timeout=30,
            max_output_bytes=65536,
        )

    async def _expire(self, sandbox_id: str, ttl_seconds: int) -> None:
        try:
            await asyncio.sleep(ttl_seconds)
            await self.terminate(sandbox_id)
        except asyncio.CancelledError:
            return

    def _get(self, sandbox_id: str) -> _Session:
        session = self._sessions.get(sandbox_id)
        if session is None:
            raise SandboxNotFound(sandbox_id)
        return session

    @staticmethod
    def _assert_live(session: _Session) -> None:
        if session.state in {
            SandboxState.TERMINATED,
            SandboxState.TERMINATING,
            SandboxState.FAILED,
        }:
            raise SandboxRuntimeError(
                f"sandbox is not executable in state {session.state}"
            )
