from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class NetworkPolicy(StrEnum):
    NONE = "NONE"
    TOOL_PROXY_ONLY = "TOOL_PROXY_ONLY"
    ALLOWLIST = "ALLOWLIST"


class SandboxState(StrEnum):
    CREATING = "CREATING"
    READY = "READY"
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    organization_id: UUID
    agent_run_id: UUID
    image: str = "lumi-sandbox:node21-v1"
    cpu_limit: float = 1.0
    memory_limit_mb: int = 512
    disk_limit_mb: int = 512
    pids_limit: int = 128
    timeout_seconds: int = 120
    network_policy: NetworkPolicy = NetworkPolicy.NONE
    max_output_bytes: int = 1_048_576
    ttl_seconds: int = 900
    allowed_hosts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.image or len(self.image) > 255:
            raise ValueError("SANDBOX_IMAGE_INVALID")
        if not 0.10 <= self.cpu_limit <= 32:
            raise ValueError("SANDBOX_CPU_LIMIT_INVALID")
        if not 64 <= self.memory_limit_mb <= 131_072:
            raise ValueError("SANDBOX_MEMORY_LIMIT_INVALID")
        if not 32 <= self.disk_limit_mb <= 131_072:
            raise ValueError("SANDBOX_DISK_LIMIT_INVALID")
        if not 8 <= self.pids_limit <= 4096:
            raise ValueError("SANDBOX_PIDS_LIMIT_INVALID")
        if not 1 <= self.timeout_seconds <= 3600:
            raise ValueError("SANDBOX_TIMEOUT_INVALID")
        if not 1024 <= self.max_output_bytes <= 64 * 1024 * 1024:
            raise ValueError("SANDBOX_MAX_OUTPUT_INVALID")
        if not 5 <= self.ttl_seconds <= 86_400:
            raise ValueError("SANDBOX_TTL_INVALID")
        if self.network_policy != NetworkPolicy.ALLOWLIST and self.allowed_hosts:
            raise ValueError("SANDBOX_ALLOWLIST_WITHOUT_POLICY")
        if self.network_policy == NetworkPolicy.ALLOWLIST and not self.allowed_hosts:
            raise ValueError("SANDBOX_ALLOWLIST_REQUIRED")


@dataclass(frozen=True, slots=True)
class ExecRequest:
    command: tuple[str, ...]
    cwd: str = "work"
    timeout_seconds: int | None = None

    def __post_init__(self) -> None:
        if not self.command or any(not part or "\x00" in part for part in self.command):
            raise ValueError("SANDBOX_COMMAND_INVALID")
        if self.timeout_seconds is not None and not 1 <= self.timeout_seconds <= 3600:
            raise ValueError("SANDBOX_EXEC_TIMEOUT_INVALID")


@dataclass(frozen=True, slots=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    duration_ms: int
    log_ref: str


@dataclass(frozen=True, slots=True)
class FileEntry:
    path: str
    kind: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class ResolvedAsset:
    asset_ref: str
    filename: str
    data: bytes
    checksum_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class CollectedArtifact:
    artifact_id: UUID
    sandbox_id: UUID
    source_path: str
    filename: str
    size_bytes: int
    checksum_sha256: str
    detected_mime: str
    storage_ref: str | None


@dataclass(frozen=True, slots=True)
class SandboxAuditRecord:
    timestamp: datetime
    sandbox_id: UUID
    organization_id: UUID
    agent_run_id: UUID
    action: str
    state: SandboxState
    image: str
    network_policy: NetworkPolicy
    command: tuple[str, ...] | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    resource: str | None = None
    detail: dict[str, str | int | bool | None] = field(default_factory=dict)
