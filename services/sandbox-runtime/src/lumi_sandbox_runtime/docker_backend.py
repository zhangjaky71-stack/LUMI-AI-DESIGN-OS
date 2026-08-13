from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

from .local_backend import (
    DockerSandboxBackend as _LocalDockerSandboxBackend,
)
from .local_backend import (
    SandboxError,
    SandboxNotFoundError,
    SandboxPolicyError,
    SandboxTimeoutError,
)
from .models import ExecRequest, ExecResult, SandboxSpec, SandboxState
from .security import (
    normalize_workspace_path,
    redact_text,
    safe_filename,
    sha256_file,
    workspace_absolute,
)

_MIB = 1024 * 1024
_WRITE_STDIN_SCRIPT = r"""
import sys
path = sys.argv[1]
with open(path, "wb") as handle:
    while True:
        chunk = sys.stdin.buffer.read(1024 * 1024)
        if not chunk:
            break
        handle.write(chunk)
""".strip()


class DockerSandboxBackend(_LocalDockerSandboxBackend):
    """Public local backend with fail-closed host and TTL hardening."""

    def create(self, spec: SandboxSpec) -> UUID:
        getuid = getattr(os, "getuid", None)
        if getuid is not None and int(getuid()) == 0:
            raise SandboxPolicyError("SANDBOX_ROOT_HOST_EXECUTION_FORBIDDEN")
        return super().create(spec)

    def exec(self, sandbox_id: UUID, request: ExecRequest) -> ExecResult:
        record = self._record(sandbox_id)
        remaining_seconds = max(
            1,
            math.ceil(record.expires_monotonic - time.monotonic()),
        )
        requested_timeout = request.timeout_seconds or record.spec.timeout_seconds
        bounded_request = replace(
            request,
            timeout_seconds=min(requested_timeout, remaining_seconds),
        )
        try:
            return super().exec(sandbox_id, bounded_request)
        finally:
            self._cleanup_exec_staging(record.root)

    def write_file(self, sandbox_id: UUID, path: str, data: bytes) -> None:
        record = self._record(sandbox_id)
        with record.lock:
            self._ensure_usable(record)
            max_bytes = min(record.spec.disk_limit_mb * _MIB, 64 * _MIB)
            if len(data) > max_bytes:
                raise SandboxPolicyError("SANDBOX_WRITE_TOO_LARGE")
            zone, _ = normalize_workspace_path(path, writable=True)
            target = workspace_absolute(path, writable=True)
            resolved = self._prepare_write_path(record, zone=zone, target=target)
            remaining_seconds = max(
                1,
                math.ceil(record.expires_monotonic - time.monotonic()),
            )
            try:
                result = subprocess.run(
                    [
                        self.docker_binary,
                        "exec",
                        "-i",
                        record.container_name,
                        "python",
                        "-c",
                        _WRITE_STDIN_SCRIPT,
                        resolved,
                    ],
                    input=data,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    timeout=min(60, remaining_seconds),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                record.state = SandboxState.FAILED
                self._best_effort_kill(record.container_name)
                self._audit(record, "sandbox.file.write_timeout", resource=path)
                raise SandboxTimeoutError("SANDBOX_WRITE_TIMEOUT") from exc
            if result.returncode != 0:
                message = redact_text(result.stderr.decode("utf-8", errors="replace"))[:1000]
                raise SandboxPolicyError(f"SANDBOX_WRITE_FAILED:{message}")
            self._audit(
                record,
                "sandbox.file.written",
                resource=path,
                detail={"bytes": len(data)},
            )

    def upload_asset(self, sandbox_id: UUID, asset_ref: str) -> str:
        record = self._record(sandbox_id)
        if self.asset_resolver is None:
            raise SandboxError("SANDBOX_ASSET_RESOLVER_NOT_CONFIGURED")
        with record.lock:
            self._ensure_usable(record)
            asset = self.asset_resolver.resolve(asset_ref)
            input_root = record.root / "input"
            max_bytes = record.spec.disk_limit_mb * _MIB
            digest = hashlib.sha256(asset.data).hexdigest()
            if asset.checksum_sha256 and digest != asset.checksum_sha256.lower():
                raise SandboxPolicyError("SANDBOX_INPUT_ASSET_CHECKSUM_MISMATCH")
            filename = safe_filename(asset.filename)
            target_name = f"{digest[:12]}-{filename}"
            target = input_root / target_name
            if target.exists():
                if not target.is_file() or target.is_symlink():
                    raise SandboxPolicyError("SANDBOX_INPUT_ASSET_TARGET_INVALID")
                if sha256_file(target) != digest:
                    raise SandboxPolicyError("SANDBOX_INPUT_ASSET_TARGET_MISMATCH")
                return f"input/{target_name}"
            used_bytes = _regular_file_bytes(input_root)
            if len(asset.data) > max_bytes or used_bytes + len(asset.data) > max_bytes:
                raise SandboxPolicyError("SANDBOX_INPUT_QUOTA_EXCEEDED")
            target.write_bytes(asset.data)
            target.chmod(0o400)
            sandbox_path = f"input/{target_name}"
            self._audit(
                record,
                "sandbox.asset.uploaded",
                resource=asset_ref,
                detail={
                    "path": sandbox_path,
                    "bytes": len(asset.data),
                    "input_bytes": used_bytes + len(asset.data),
                },
            )
            return sandbox_path

    def reap_expired(self) -> tuple[UUID, ...]:
        now = time.monotonic()
        with self._records_lock:
            expired_records = tuple(
                record
                for record in self._records.values()
                if record.state not in {
                    SandboxState.TERMINATED,
                    SandboxState.TERMINATING,
                }
                and record.expires_monotonic <= now
            )
        for record in expired_records:
            # Kill first without waiting for the execution lock. A running docker exec
            # then exits promptly; terminate can acquire the lock and remove workspace.
            self._best_effort_kill(record.container_name)
            self.terminate(record.sandbox_id)
        return tuple(record.sandbox_id for record in expired_records)

    def _persist_logs(
        self,
        record: Any,
        exec_id: str,
        stdout_path: Path,
        stderr_path: Path,
    ) -> str:
        sandbox_id = record.sandbox_id
        spec = record.spec
        destination_dir = self.log_root / str(sandbox_id)
        destination_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        destination = destination_dir / f"{exec_id}.log"
        per_stream = min(spec.max_output_bytes * 2, 8 * _MIB)
        stdout = _read_prefix(stdout_path, per_stream)
        stderr = _read_prefix(stderr_path, per_stream)
        content = "[stdout]\n" + redact_text(stdout) + "\n[stderr]\n" + redact_text(stderr)
        destination.write_text(content, encoding="utf-8")
        destination.chmod(0o600)
        total_budget = min(
            max(spec.max_output_bytes * 16, 8 * _MIB),
            min(spec.disk_limit_mb * _MIB, 64 * _MIB),
        )
        _prune_oldest_files(destination_dir, total_budget, keep=destination)
        return f"sandbox-log:{sandbox_id}:{exec_id}"

    @staticmethod
    def _cleanup_exec_staging(root: Path) -> None:
        staging = root / "staging"
        if not staging.exists():
            return
        for candidate in staging.glob("exec-*"):
            if candidate.is_dir() and not candidate.is_symlink():
                shutil.rmtree(candidate, ignore_errors=True)


def _regular_file_bytes(root: Path) -> int:
    total = 0
    for path in root.iterdir():
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
    return total


def _read_prefix(path: Path, limit: int) -> str:
    with path.open("rb") as handle:
        return handle.read(limit).decode("utf-8", errors="replace")


def _prune_oldest_files(directory: Path, budget_bytes: int, *, keep: Path) -> None:
    files = [
        path
        for path in directory.glob("*.log")
        if path.is_file() and not path.is_symlink()
    ]
    total = sum(path.stat().st_size for path in files)
    if total <= budget_bytes:
        return
    for path in sorted(files, key=lambda item: item.stat().st_mtime_ns):
        if path == keep:
            continue
        size = path.stat().st_size
        path.unlink(missing_ok=True)
        total -= size
        if total <= budget_bytes:
            break


__all__ = [
    "DockerSandboxBackend",
    "SandboxError",
    "SandboxNotFoundError",
    "SandboxPolicyError",
    "SandboxTimeoutError",
]
