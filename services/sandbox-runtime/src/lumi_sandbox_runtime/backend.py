from __future__ import annotations

from typing import Protocol

from .models import (
    AssetInputRef,
    CollectedArtifact,
    ExecResult,
    FileEntry,
    SandboxCommand,
    SandboxHandle,
    SandboxSpec,
)


class ArtifactStoragePort(Protocol):
    async def put_validated_output(
        self,
        *,
        organization_id: str,
        sandbox_id: str,
        path: str,
        content: bytes,
        sha256: str,
        detected_mime: str,
    ) -> str: ...


class SandboxBackend(Protocol):
    async def create(self, spec: SandboxSpec) -> SandboxHandle: ...

    async def exec(self, sandbox_id: str, command: SandboxCommand) -> ExecResult: ...

    async def read_file(self, sandbox_id: str, path: str) -> bytes: ...

    async def write_file(self, sandbox_id: str, path: str, content: bytes) -> None: ...

    async def list_files(self, sandbox_id: str, path: str) -> list[FileEntry]: ...

    async def upload_asset(self, sandbox_id: str, asset: AssetInputRef) -> str: ...

    async def collect_artifact(self, sandbox_id: str, path: str) -> CollectedArtifact: ...

    async def terminate(self, sandbox_id: str) -> None: ...
