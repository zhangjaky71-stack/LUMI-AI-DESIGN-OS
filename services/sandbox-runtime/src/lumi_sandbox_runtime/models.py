from __future__ import annotations

import re
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
        disk_bytes = self.disk_limit_mb * 1024 * 1024
        if self.max_output_bytes > disk_bytes // 4:
            raise ValueError("SANDBOX_OUTPUT_BUDGET_EXCEEDS_STORAGE")
        if not 5 <= self.ttl_seconds <= 86_400:
            raise ValueError("SANDBOX_TTL_INVALID")
        if self.network_policy != NetworkPolicy.ALLOWLIST and self.allowed_hosts:
            raise ValueError("SANDBOX_ALLOWLIST_WITHOUT_POLICY")
        if self.network_policy == NetworkPolicy.ALLOWLIST and not self.allowed_hosts:
            raise ValueError("SANDBOX_ALLOWLIST_REQUIRED")


_EXCHANGE_KEY_PREFIX = "sandbox-exchange/v1/"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_EXCHANGE_FILE_BYTES = 8 * 1024 * 1024 * 1024


def _validate_exchange_key(value: str) -> None:
    if (
        not value.startswith(_EXCHANGE_KEY_PREFIX)
        or len(value) > 1024
        or "\x00" in value
        or "\n" in value
        or "\r" in value
        or "//" in value
        or "/../" in value
        or value.endswith("/..")
    ):
        raise ValueError("SANDBOX_EXCHANGE_KEY_INVALID")


def _validate_exchange_path(value: str, *, prefix: str) -> None:
    if (
        not value.startswith(prefix)
        or value.startswith("/")
        or len(value) > 512
        or "\\" in value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
        or "//" in value
        or "/../" in value
        or value.endswith("/..")
        or value in {prefix.rstrip("/"), ".", ".."}
    ):
        raise ValueError("SANDBOX_EXCHANGE_PATH_INVALID")


def _validate_exchange_file_limit(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= _MAX_EXCHANGE_FILE_BYTES:
        raise ValueError("SANDBOX_EXCHANGE_FILE_LIMIT_INVALID")


@dataclass(frozen=True, slots=True)
class ExchangeInputFile:
    exchange_key: str
    path: str
    max_bytes: int
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        _validate_exchange_key(self.exchange_key)
        _validate_exchange_path(self.path, prefix="input/")
        _validate_exchange_file_limit(self.max_bytes)
        if self.expected_sha256 is not None and not _SHA256.fullmatch(self.expected_sha256):
            raise ValueError("SANDBOX_EXCHANGE_SHA256_INVALID")


@dataclass(frozen=True, slots=True)
class ExchangeOutputFile:
    exchange_key: str
    path: str
    max_bytes: int
    content_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        _validate_exchange_key(self.exchange_key)
        _validate_exchange_path(self.path, prefix="output/")
        _validate_exchange_file_limit(self.max_bytes)
        if (
            not self.content_type
            or len(self.content_type) > 255
            or "\x00" in self.content_type
            or "\n" in self.content_type
            or "\r" in self.content_type
        ):
            raise ValueError("SANDBOX_EXCHANGE_CONTENT_TYPE_INVALID")


@dataclass(frozen=True, slots=True)
class ExecRequest:
    command: tuple[str, ...]
    cwd: str = "work"
    timeout_seconds: int | None = None
    exchange_inputs: tuple[ExchangeInputFile, ...] = ()
    exchange_outputs: tuple[ExchangeOutputFile, ...] = ()

    def __post_init__(self) -> None:
        if not self.command or any(not part or "\x00" in part for part in self.command):
            raise ValueError("SANDBOX_COMMAND_INVALID")
        if self.timeout_seconds is not None and not 1 <= self.timeout_seconds <= 3600:
            raise ValueError("SANDBOX_EXEC_TIMEOUT_INVALID")
        if self.cwd not in {"work", "input", "output"}:
            raise ValueError("SANDBOX_EXEC_CWD_INVALID")
        if len(self.exchange_inputs) > 64 or len(self.exchange_outputs) > 16:
            raise ValueError("SANDBOX_EXCHANGE_FILE_COUNT_INVALID")
        paths = [item.path for item in self.exchange_inputs] + [
            item.path for item in self.exchange_outputs
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("SANDBOX_EXCHANGE_PATH_DUPLICATE")
        keys = [item.exchange_key for item in self.exchange_inputs] + [
            item.exchange_key for item in self.exchange_outputs
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("SANDBOX_EXCHANGE_KEY_DUPLICATE")


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
