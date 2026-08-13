from __future__ import annotations

import math
import time
from dataclasses import replace
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
from .models import ExecRequest, ExecResult, SandboxState


class DockerSandboxBackend(_LocalDockerSandboxBackend):
    """Public local backend with TTL enforcement across active executions."""

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
        return super().exec(sandbox_id, bounded_request)

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


__all__ = [
    "DockerSandboxBackend",
    "SandboxError",
    "SandboxNotFoundError",
    "SandboxPolicyError",
    "SandboxTimeoutError",
]
