from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from .audit import JsonlAuditSink
from .models import (
    CollectedArtifact,
    ExecRequest,
    ExecResult,
    FileEntry,
    NetworkPolicy,
    SandboxAuditRecord,
    SandboxSpec,
    SandboxState,
)
from .ports import ArtifactSink, AssetResolver, AuditSink
from .security import (
    normalize_workspace_path,
    redact_command,
    redact_text,
    safe_filename,
    sha256_file,
    sniff_mime,
    validate_command,
    workspace_absolute,
)

_RESOLVE_SCRIPT = r"""
import os, stat, sys
root = os.path.realpath(sys.argv[1])
target = os.path.realpath(sys.argv[2])
expected = sys.argv[3]
if target != root and not target.startswith(root + os.sep):
    raise SystemExit(42)
st = os.stat(target)
if expected == "file" and not stat.S_ISREG(st.st_mode):
    raise SystemExit(43)
if expected == "dir" and not stat.S_ISDIR(st.st_mode):
    raise SystemExit(44)
print(target)
""".strip()

_PREPARE_WRITE_SCRIPT = r"""
import os, sys
root = os.path.realpath(sys.argv[1])
target = sys.argv[2]
parent = os.path.realpath(os.path.dirname(target))
if parent != root and not parent.startswith(root + os.sep):
    raise SystemExit(42)
os.makedirs(parent, exist_ok=True)
resolved = os.path.realpath(target)
if resolved != root and not resolved.startswith(root + os.sep):
    raise SystemExit(42)
print(resolved)
""".strip()

_LIST_SCRIPT = r"""
import json, os, stat, sys
root = os.path.realpath(sys.argv[1])
target = os.path.realpath(sys.argv[2])
limit = int(sys.argv[3])
if target != root and not target.startswith(root + os.sep):
    raise SystemExit(42)
names = sorted(os.listdir(target))
if len(names) > limit:
    raise SystemExit(46)
entries = []
for name in names:
    path = os.path.join(target, name)
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        kind, size = "symlink", None
    elif stat.S_ISDIR(st.st_mode):
        kind, size = "directory", None
    elif stat.S_ISREG(st.st_mode):
        kind, size = "file", st.st_size
    else:
        kind, size = "other", None
    entries.append({"path": name, "kind": kind, "size_bytes": size})
print(json.dumps(entries, separators=(",", ":")))
""".strip()

_STRAY_SCRIPT = r"""
import os
self_pid = os.getpid()
stray = []
for name in os.listdir("/proc"):
    if not name.isdigit():
        continue
    pid = int(name)
    if pid in {1, self_pid}:
        continue
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8") as handle:
            comm = handle.read().strip()
    except OSError:
        continue
    if comm not in {"tail", "tini"}:
        stray.append({"pid": pid, "comm": comm})
print(stray)
raise SystemExit(45 if stray else 0)
""".strip()


class SandboxError(RuntimeError):
    pass


class SandboxNotFoundError(SandboxError):
    pass


class SandboxTimeoutError(SandboxError):
    pass


class SandboxPolicyError(SandboxError):
    pass


@dataclass(slots=True)
class _SandboxRecord:
    sandbox_id: UUID
    spec: SandboxSpec
    container_name: str
    root: Path
    state: SandboxState
    created_monotonic: float
    expires_monotonic: float
    lock: threading.RLock


class DockerSandboxBackend:
    """Local/CI backend; Agent data never becomes a host shell string."""

    def __init__(
        self,
        *,
        runtime_root: Path | None = None,
        audit_sink: AuditSink | None = None,
        asset_resolver: AssetResolver | None = None,
        artifact_sink: ArtifactSink | None = None,
        docker_binary: str = "docker",
    ) -> None:
        self.runtime_root = runtime_root or Path(tempfile.gettempdir()) / "lumi-sandbox-runtime"
        if "," in str(self.runtime_root):
            raise ValueError("SANDBOX_RUNTIME_ROOT_INVALID")
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.log_root = self.runtime_root / "_logs"
        self.log_root.mkdir(parents=True, exist_ok=True)
        self.audit_sink = audit_sink or JsonlAuditSink(
            self.runtime_root / "_audit" / "sandbox.jsonl"
        )
        self.asset_resolver = asset_resolver
        self.artifact_sink = artifact_sink
        self.docker_binary = docker_binary
        self._records: dict[UUID, _SandboxRecord] = {}
        self._records_lock = threading.RLock()

    def create(self, spec: SandboxSpec) -> UUID:
        if spec.network_policy != NetworkPolicy.NONE:
            raise SandboxPolicyError(
                "NODE-21 local backend supports only deny-all network; proxy policies require "
                "a dedicated egress adapter"
            )
        if shutil.which(self.docker_binary) is None:
            raise SandboxError("SANDBOX_DOCKER_NOT_AVAILABLE")
        sandbox_id = uuid4()
        root = self.runtime_root / str(sandbox_id)
        input_root = root / "input"
        staging_root = root / "staging"
        input_root.mkdir(parents=True, mode=0o700)
        staging_root.mkdir(parents=True, mode=0o700)
        (self.log_root / str(sandbox_id)).mkdir(parents=True, mode=0o700)
        container_name = f"lumi-sbx-{sandbox_id.hex[:16]}"
        now = time.monotonic()
        record = _SandboxRecord(
            sandbox_id=sandbox_id,
            spec=spec,
            container_name=container_name,
            root=root,
            state=SandboxState.CREATING,
            created_monotonic=now,
            expires_monotonic=now + spec.ttl_seconds,
            lock=threading.RLock(),
        )
        with self._records_lock:
            self._records[sandbox_id] = record
        self._audit(record, "sandbox.create.requested")
        uid = _host_uid()
        gid = _host_gid()
        work_mb, output_mb, tmp_mb = _tmpfs_budgets(spec.disk_limit_mb)
        expires_epoch = int(time.time()) + spec.ttl_seconds
        options = f"rw,nosuid,nodev,uid={uid},gid={gid},mode=0700"
        create_args = [
            "create",
            "--name",
            container_name,
            "--label",
            "lumi.sandbox.runtime=node21",
            "--label",
            f"lumi.sandbox.id={sandbox_id}",
            "--label",
            f"lumi.organization.id={spec.organization_id}",
            "--label",
            f"lumi.agent_run.id={spec.agent_run_id}",
            "--label",
            f"lumi.sandbox.expires_at={expires_epoch}",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(spec.pids_limit),
            "--memory",
            f"{spec.memory_limit_mb}m",
            "--memory-swap",
            f"{spec.memory_limit_mb}m",
            "--cpus",
            str(spec.cpu_limit),
            "--ulimit",
            "nofile=256:256",
            "--user",
            f"{uid}:{gid}",
            "--env",
            "HOME=/tmp",
            "--env",
            "TMPDIR=/tmp",
            "--env",
            f"LUMI_SANDBOX_ID={sandbox_id}",
            "--mount",
            f"type=bind,src={input_root},dst=/workspace/input,readonly",
            "--tmpfs",
            f"/workspace/work:{options},size={work_mb}m",
            "--tmpfs",
            f"/workspace/output:{options},size={output_mb}m",
            "--tmpfs",
            f"/tmp:{options},noexec,size={tmp_mb}m",
            "--workdir",
            "/workspace/work",
            "--stop-timeout",
            "2",
            spec.image,
        ]
        try:
            self._docker(create_args, timeout=60)
            self._docker(["start", container_name], timeout=30)
        except Exception:
            record.state = SandboxState.FAILED
            self._audit(record, "sandbox.create.failed")
            self._best_effort_remove(container_name)
            shutil.rmtree(root, ignore_errors=True)
            raise
        record.state = SandboxState.READY
        self._audit(record, "sandbox.created")
        return sandbox_id

    def state(self, sandbox_id: UUID) -> SandboxState:
        return self._record(sandbox_id).state

    def exec(self, sandbox_id: UUID, request: ExecRequest) -> ExecResult:
        record = self._record(sandbox_id)
        with record.lock:
            self._ensure_usable(record)
            validate_command(request.command)
            cwd = self._resolve_container_path(record, request.cwd, expected="dir")
            timeout = min(request.timeout_seconds or record.spec.timeout_seconds, 3600)
            safe_command = redact_command(request.command)
            record.state = SandboxState.RUNNING
            self._audit(record, "sandbox.exec.started", command=safe_command)
            exec_id = uuid4().hex
            transient = record.root / "staging" / f"exec-{exec_id}"
            transient.mkdir(parents=True, mode=0o700)
            stdout_path = transient / "stdout.log"
            stderr_path = transient / "stderr.log"
            started = time.monotonic()
            process = subprocess.Popen(
                [
                    self.docker_binary,
                    "exec",
                    "--workdir",
                    cwd,
                    record.container_name,
                    *request.command,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
            log_cap = min(record.spec.max_output_bytes * 8, 64 * 1024 * 1024)
            stdout_thread = _stream_to_file(process.stdout, stdout_path, log_cap)
            stderr_thread = _stream_to_file(process.stderr, stderr_path, log_cap)
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                self._best_effort_kill(record.container_name)
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                duration_ms = int((time.monotonic() - started) * 1000)
                self._persist_logs(record, exec_id, stdout_path, stderr_path)
                record.state = SandboxState.FAILED
                self._audit(
                    record,
                    "sandbox.exec.timeout",
                    command=safe_command,
                    duration_ms=duration_ms,
                )
                raise SandboxTimeoutError("SANDBOX_EXEC_TIMEOUT") from exc
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout, stdout_truncated = _read_limited(
                stdout_path,
                record.spec.max_output_bytes,
            )
            stderr, stderr_truncated = _read_limited(
                stderr_path,
                record.spec.max_output_bytes,
            )
            log_ref = self._persist_logs(record, exec_id, stdout_path, stderr_path)
            if not self._no_stray_processes(record):
                record.state = SandboxState.FAILED
                self._best_effort_kill(record.container_name)
                self._audit(
                    record,
                    "sandbox.exec.stray_process",
                    command=safe_command,
                    exit_code=exit_code,
                    duration_ms=duration_ms,
                )
                raise SandboxPolicyError("SANDBOX_STRAY_PROCESS_DETECTED")
            record.state = SandboxState.IDLE
            self._audit(
                record,
                "sandbox.exec.completed",
                command=safe_command,
                exit_code=exit_code,
                duration_ms=duration_ms,
                detail={
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                },
            )
            return ExecResult(
                exit_code=exit_code,
                stdout=redact_text(stdout),
                stderr=redact_text(stderr),
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                duration_ms=duration_ms,
                log_ref=log_ref,
            )

    def read_file(
        self,
        sandbox_id: UUID,
        path: str,
        *,
        max_bytes: int | None = None,
    ) -> bytes:
        record = self._record(sandbox_id)
        with record.lock:
            self._ensure_usable(record)
            resolved = self._resolve_container_path(record, path, expected="file")
            limit = max_bytes or record.spec.max_output_bytes
            if not 1 <= limit <= 64 * 1024 * 1024:
                raise ValueError("SANDBOX_READ_LIMIT_INVALID")
            with tempfile.TemporaryDirectory(dir=record.root / "staging") as temp_dir:
                target = Path(temp_dir) / "file"
                self._docker(
                    ["cp", f"{record.container_name}:{resolved}", str(target)],
                    timeout=30,
                )
                if target.is_symlink() or not target.is_file():
                    raise SandboxPolicyError("SANDBOX_FILE_TYPE_FORBIDDEN")
                if target.stat().st_size > limit:
                    raise SandboxPolicyError("SANDBOX_FILE_TOO_LARGE")
                data = target.read_bytes()
            self._audit(
                record,
                "sandbox.file.read",
                resource=path,
                detail={"bytes": len(data)},
            )
            return data

    def write_file(self, sandbox_id: UUID, path: str, data: bytes) -> None:
        record = self._record(sandbox_id)
        with record.lock:
            self._ensure_usable(record)
            max_bytes = record.spec.disk_limit_mb * 1024 * 1024
            if len(data) > max_bytes:
                raise SandboxPolicyError("SANDBOX_WRITE_TOO_LARGE")
            zone, _ = normalize_workspace_path(path, writable=True)
            target = workspace_absolute(path, writable=True)
            resolved = self._prepare_write_path(record, zone=zone, target=target)
            with tempfile.NamedTemporaryFile(
                dir=record.root / "staging",
                delete=False,
            ) as handle:
                handle.write(data)
                staged = Path(handle.name)
            try:
                self._docker(
                    ["cp", str(staged), f"{record.container_name}:{resolved}"],
                    timeout=30,
                )
            finally:
                staged.unlink(missing_ok=True)
            self._audit(
                record,
                "sandbox.file.written",
                resource=path,
                detail={"bytes": len(data)},
            )

    def list_files(self, sandbox_id: UUID, path: str) -> tuple[FileEntry, ...]:
        record = self._record(sandbox_id)
        with record.lock:
            self._ensure_usable(record)
            zone, _ = normalize_workspace_path(path)
            target = workspace_absolute(path)
            root = f"/workspace/{zone}"
            result = self._exec_internal(
                record,
                ["python", "-c", _LIST_SCRIPT, root, target, "5000"],
            )
            if result.returncode == 46:
                raise SandboxPolicyError("SANDBOX_DIRECTORY_TOO_LARGE")
            if result.returncode != 0:
                raise SandboxPolicyError("SANDBOX_LIST_PATH_INVALID")
            raw = json.loads(result.stdout)
            entries = tuple(
                FileEntry(
                    path=f"{path.rstrip('/')}/{item['path']}",
                    kind=item["kind"],
                    size_bytes=item["size_bytes"],
                )
                for item in raw
            )
            self._audit(
                record,
                "sandbox.file.listed",
                resource=path,
                detail={"count": len(entries)},
            )
            return entries

    def upload_asset(self, sandbox_id: UUID, asset_ref: str) -> str:
        record = self._record(sandbox_id)
        if self.asset_resolver is None:
            raise SandboxError("SANDBOX_ASSET_RESOLVER_NOT_CONFIGURED")
        with record.lock:
            self._ensure_usable(record)
            asset = self.asset_resolver.resolve(asset_ref)
            max_bytes = record.spec.disk_limit_mb * 1024 * 1024
            if len(asset.data) > max_bytes:
                raise SandboxPolicyError("SANDBOX_INPUT_ASSET_TOO_LARGE")
            digest = hashlib.sha256(asset.data).hexdigest()
            if asset.checksum_sha256 and digest != asset.checksum_sha256.lower():
                raise SandboxPolicyError("SANDBOX_INPUT_ASSET_CHECKSUM_MISMATCH")
            filename = safe_filename(asset.filename)
            target_name = f"{digest[:12]}-{filename}"
            target = record.root / "input" / target_name
            target.write_bytes(asset.data)
            target.chmod(0o400)
            sandbox_path = f"input/{target_name}"
            self._audit(
                record,
                "sandbox.asset.uploaded",
                resource=asset_ref,
                detail={"path": sandbox_path, "bytes": len(asset.data)},
            )
            return sandbox_path

    def collect_artifact(self, sandbox_id: UUID, path: str) -> CollectedArtifact:
        record = self._record(sandbox_id)
        with record.lock:
            self._ensure_usable(record)
            zone, relative = normalize_workspace_path(path)
            if zone != "output" or not relative:
                raise SandboxPolicyError("SANDBOX_ARTIFACT_MUST_BE_OUTPUT_FILE")
            resolved = self._resolve_container_path(record, path, expected="file")
            with tempfile.TemporaryDirectory(dir=record.root / "staging") as temp_dir:
                staged = Path(temp_dir) / safe_filename(Path(relative).name)
                self._docker(
                    ["cp", f"{record.container_name}:{resolved}", str(staged)],
                    timeout=60,
                )
                if staged.is_symlink() or not staged.is_file():
                    raise SandboxPolicyError("SANDBOX_ARTIFACT_FILE_TYPE_INVALID")
                size = staged.stat().st_size
                max_bytes = record.spec.disk_limit_mb * 1024 * 1024
                if size > max_bytes:
                    raise SandboxPolicyError("SANDBOX_ARTIFACT_TOO_LARGE")
                checksum = sha256_file(staged)
                detected_mime = sniff_mime(staged)
                storage_ref = None
                if self.artifact_sink is not None:
                    storage_ref = self.artifact_sink.store_file(
                        organization_id=record.spec.organization_id,
                        agent_run_id=record.spec.agent_run_id,
                        sandbox_id=sandbox_id,
                        filename=staged.name,
                        source=staged,
                        checksum_sha256=checksum,
                        detected_mime=detected_mime,
                    )
            artifact = CollectedArtifact(
                artifact_id=uuid4(),
                sandbox_id=sandbox_id,
                source_path=path,
                filename=safe_filename(Path(relative).name),
                size_bytes=size,
                checksum_sha256=checksum,
                detected_mime=detected_mime,
                storage_ref=storage_ref,
            )
            self._audit(
                record,
                "sandbox.artifact.collected",
                resource=path,
                detail={
                    "bytes": size,
                    "checksum_sha256": checksum,
                    "detected_mime": detected_mime,
                    "stored": storage_ref is not None,
                },
            )
            return artifact

    def terminate(self, sandbox_id: UUID) -> None:
        record = self._record(sandbox_id)
        with record.lock:
            if record.state == SandboxState.TERMINATED:
                return
            record.state = SandboxState.TERMINATING
            self._audit(record, "sandbox.terminate.requested")
            self._best_effort_remove(record.container_name)
            shutil.rmtree(record.root, ignore_errors=True)
            record.state = SandboxState.TERMINATED
            self._audit(record, "sandbox.terminated")

    def reap_expired(self) -> tuple[UUID, ...]:
        now = time.monotonic()
        with self._records_lock:
            expired = tuple(
                sandbox_id
                for sandbox_id, record in self._records.items()
                if record.state not in {
                    SandboxState.TERMINATED,
                    SandboxState.TERMINATING,
                }
                and record.expires_monotonic <= now
            )
        for sandbox_id in expired:
            self.terminate(sandbox_id)
        return expired

    def reap_orphaned_containers(self) -> tuple[str, ...]:
        result = self._docker(
            ["ps", "-aq", "--filter", "label=lumi.sandbox.runtime=node21"],
            timeout=30,
            allow_failure=True,
        )
        removed: list[str] = []
        now = int(time.time())
        for container_id in result.stdout.split():
            inspect = self._docker(
                [
                    "inspect",
                    "--format",
                    "{{ index .Config.Labels \"lumi.sandbox.expires_at\" }}",
                    container_id,
                ],
                timeout=10,
                allow_failure=True,
            )
            try:
                expires = int(inspect.stdout.strip())
            except ValueError:
                continue
            if expires <= now:
                self._best_effort_remove(container_id)
                removed.append(container_id)
        return tuple(removed)

    def _record(self, sandbox_id: UUID) -> _SandboxRecord:
        with self._records_lock:
            try:
                return self._records[sandbox_id]
            except KeyError as exc:
                raise SandboxNotFoundError("SANDBOX_NOT_FOUND") from exc

    def _ensure_usable(self, record: _SandboxRecord) -> None:
        if record.state in {
            SandboxState.FAILED,
            SandboxState.TERMINATING,
            SandboxState.TERMINATED,
        }:
            raise SandboxError(f"SANDBOX_NOT_USABLE:{record.state}")
        if record.expires_monotonic <= time.monotonic():
            self.terminate(record.sandbox_id)
            raise SandboxError("SANDBOX_EXPIRED")

    def _resolve_container_path(
        self,
        record: _SandboxRecord,
        path: str,
        *,
        expected: str,
    ) -> str:
        zone, _ = normalize_workspace_path(path)
        target = workspace_absolute(path)
        root = f"/workspace/{zone}"
        result = self._exec_internal(
            record,
            ["python", "-c", _RESOLVE_SCRIPT, root, target, expected],
        )
        if result.returncode != 0:
            raise SandboxPolicyError("SANDBOX_PATH_RESOLUTION_FAILED")
        return result.stdout.strip()

    def _prepare_write_path(
        self,
        record: _SandboxRecord,
        *,
        zone: str,
        target: str,
    ) -> str:
        root = f"/workspace/{zone}"
        result = self._exec_internal(
            record,
            ["python", "-c", _PREPARE_WRITE_SCRIPT, root, target],
        )
        if result.returncode != 0:
            raise SandboxPolicyError("SANDBOX_WRITE_PATH_RESOLUTION_FAILED")
        return result.stdout.strip()

    def _exec_internal(
        self,
        record: _SandboxRecord,
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        return self._docker(
            ["exec", record.container_name, *command],
            timeout=15,
            allow_failure=True,
        )

    def _no_stray_processes(self, record: _SandboxRecord) -> bool:
        result = self._exec_internal(record, ["python", "-c", _STRAY_SCRIPT])
        return result.returncode == 0

    def _persist_logs(
        self,
        record: _SandboxRecord,
        exec_id: str,
        stdout_path: Path,
        stderr_path: Path,
    ) -> str:
        destination = self.log_root / str(record.sandbox_id) / f"{exec_id}.log"
        stdout = _read_all_text(stdout_path)
        stderr = _read_all_text(stderr_path)
        content = "[stdout]\n" + redact_text(stdout) + "\n[stderr]\n" + redact_text(stderr)
        destination.write_text(content, encoding="utf-8")
        destination.chmod(0o600)
        return f"sandbox-log:{record.sandbox_id}:{exec_id}"

    def _audit(
        self,
        record: _SandboxRecord,
        action: str,
        *,
        command: tuple[str, ...] | None = None,
        exit_code: int | None = None,
        duration_ms: int | None = None,
        resource: str | None = None,
        detail: dict[str, str | int | bool | None] | None = None,
    ) -> None:
        self.audit_sink.emit(
            SandboxAuditRecord(
                timestamp=datetime.now(UTC),
                sandbox_id=record.sandbox_id,
                organization_id=record.spec.organization_id,
                agent_run_id=record.spec.agent_run_id,
                action=action,
                state=record.state,
                image=record.spec.image,
                network_policy=record.spec.network_policy,
                command=command,
                exit_code=exit_code,
                duration_ms=duration_ms,
                resource=resource,
                detail=detail or {},
            )
        )

    def _docker(
        self,
        args: list[str],
        *,
        timeout: int,
        allow_failure: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [self.docker_binary, *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0 and not allow_failure:
            message = redact_text(result.stderr.strip())[:2000]
            raise SandboxError(f"SANDBOX_DOCKER_COMMAND_FAILED:{message}")
        return result

    def _best_effort_remove(self, container: str) -> None:
        try:
            self._docker(
                ["rm", "-f", "-v", container],
                timeout=20,
                allow_failure=True,
            )
        except Exception:
            pass

    def _best_effort_kill(self, container: str) -> None:
        try:
            self._docker(["kill", container], timeout=10, allow_failure=True)
        except Exception:
            pass


def _host_uid() -> int:
    getter = getattr(os, "getuid", None)
    return int(getter()) if getter is not None else 65532


def _host_gid() -> int:
    getter = getattr(os, "getgid", None)
    return int(getter()) if getter is not None else 65532


def _tmpfs_budgets(total_mb: int) -> tuple[int, int, int]:
    work = max(1, int(total_mb * 0.60))
    output = max(1, int(total_mb * 0.30))
    temp = max(1, total_mb - work - output)
    return work, output, temp


def _stream_to_file(stream: BinaryIO | None, path: Path, cap: int) -> threading.Thread:
    def drain() -> None:
        if stream is None:
            path.write_bytes(b"")
            return
        written = 0
        with path.open("wb") as handle:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                remaining = cap - written
                if remaining > 0:
                    handle.write(chunk[:remaining])
                    written += min(len(chunk), remaining)
        stream.close()

    thread = threading.Thread(target=drain, daemon=True)
    thread.start()
    return thread


def _read_limited(path: Path, limit: int) -> tuple[str, bool]:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", errors="replace"), truncated


def _read_all_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="replace")
