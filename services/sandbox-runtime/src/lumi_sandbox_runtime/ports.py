from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import UUID

from .models import (
    CollectedArtifact,
    ExecRequest,
    ExecResult,
    FileEntry,
    ResolvedAsset,
    SandboxAuditRecord,
    SandboxSpec,
    SandboxState,
)


class AuditSink(Protocol):
    def emit(self, record: SandboxAuditRecord) -> None: ...


class AssetResolver(Protocol):
    def resolve(self, asset_ref: str) -> ResolvedAsset: ...


class ArtifactSink(Protocol):
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
    ) -> str: ...


class SandboxBackend(Protocol):
    def create(self, spec: SandboxSpec) -> UUID: ...

    def state(self, sandbox_id: UUID) -> SandboxState: ...

    def exec(self, sandbox_id: UUID, request: ExecRequest) -> ExecResult: ...

    def read_file(
        self,
        sandbox_id: UUID,
        path: str,
        *,
        max_bytes: int | None = None,
    ) -> bytes: ...

    def write_file(self, sandbox_id: UUID, path: str, data: bytes) -> None: ...

    def list_files(self, sandbox_id: UUID, path: str) -> tuple[FileEntry, ...]: ...

    def upload_asset(self, sandbox_id: UUID, asset_ref: str) -> str: ...

    def collect_artifact(self, sandbox_id: UUID, path: str) -> CollectedArtifact: ...

    def terminate(self, sandbox_id: UUID) -> None: ...

    def reap_expired(self) -> tuple[UUID, ...]: ...
