from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NetworkPolicy(StrEnum):
    NONE = "none"
    TOOL_PROXY_ONLY = "tool_proxy_only"
    ALLOWLIST = "allowlist"


class SandboxState(StrEnum):
    CREATING = "creating"
    READY = "ready"
    RUNNING = "running"
    IDLE = "idle"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"


class AuditAction(StrEnum):
    CREATE = "create"
    EXEC = "exec"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    LIST_FILES = "list_files"
    UPLOAD_ASSET = "upload_asset"
    COLLECT_ARTIFACT = "collect_artifact"
    TERMINATE = "terminate"
    SECURITY_DENY = "security_deny"


class SandboxAccessContext(FrozenModel):
    organization_id: UUID
    agent_run_id: UUID
    actor_id: UUID | None = None
    trace_id: str | None = Field(default=None, max_length=128)


class SandboxSpec(FrozenModel):
    organization_id: UUID
    agent_run_id: UUID
    image: str = Field(min_length=1, max_length=255)
    image_version: str = Field(min_length=1, max_length=120)
    cpu_limit: float = Field(default=1.0, gt=0, le=16)
    memory_limit_mb: int = Field(default=1024, ge=128, le=32768)
    disk_limit_mb: int = Field(default=2048, ge=64, le=65536)
    pids_limit: int = Field(default=128, ge=16, le=4096)
    timeout_seconds: int = Field(default=900, ge=1, le=86400)
    command_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    network_policy: NetworkPolicy = NetworkPolicy.NONE
    network_allowlist: tuple[str, ...] = ()
    max_output_bytes: int = Field(default=1_048_576, ge=1024, le=16_777_216)
    ttl_seconds: int = Field(default=1800, ge=30, le=86400)

    @model_validator(mode="after")
    def validate_network(self) -> "SandboxSpec":
        if self.network_policy is NetworkPolicy.ALLOWLIST and not self.network_allowlist:
            raise ValueError("ALLOWLIST requires at least one destination")
        if self.network_policy is not NetworkPolicy.ALLOWLIST and self.network_allowlist:
            raise ValueError("network_allowlist is only valid with ALLOWLIST policy")
        return self


class SandboxCommand(FrozenModel):
    argv: tuple[str, ...] = Field(min_length=1, max_length=256)
    cwd: str = "/workspace/work"
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("argv")
    @classmethod
    def non_empty_arguments(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any("\x00" in item for item in value):
            raise ValueError("command arguments cannot contain NUL")
        return value


class ResourceUsage(FrozenModel):
    wall_time_ms: int = Field(ge=0)
    stdout_bytes: int = Field(ge=0)
    stderr_bytes: int = Field(ge=0)
    output_truncated: bool = False


class ExecResult(FrozenModel):
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    usage: ResourceUsage


class FileEntry(FrozenModel):
    path: str
    size: int = Field(ge=0)
    is_directory: bool = False


class AssetInputRef(FrozenModel):
    asset_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    content: bytes
    declared_mime: str | None = Field(default=None, max_length=255)


class CollectedArtifact(FrozenModel):
    sandbox_id: str
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    detected_mime: str
    storage_ref: str | None = None


class SandboxHandle(FrozenModel):
    sandbox_id: str = Field(min_length=1, max_length=160)
    organization_id: UUID
    agent_run_id: UUID
    state: SandboxState
    image_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime


class SandboxAuditEvent(FrozenModel):
    sandbox_id: str
    organization_id: UUID
    agent_run_id: UUID
    action: AuditAction
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    image_version: str
    network_policy: NetworkPolicy
    command: tuple[str, ...] | None = None
    exit_code: int | None = None
    usage: ResourceUsage | None = None
    path: str | None = None
    result_ref: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
