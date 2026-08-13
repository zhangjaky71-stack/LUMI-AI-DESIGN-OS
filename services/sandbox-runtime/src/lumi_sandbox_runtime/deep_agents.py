from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from .models import ExecRequest
from .ports import SandboxBackend


class DeepAgentSandboxTools:
    """Narrow tool surface for Deep Agents; never exposes Docker or host subprocess APIs."""

    def __init__(self, backend: SandboxBackend, sandbox_id: UUID) -> None:
        self._backend = backend
        self._sandbox_id = sandbox_id

    def execute(self, command: list[str], *, cwd: str = "work", timeout: int | None = None) -> dict:
        result = self._backend.exec(
            self._sandbox_id,
            ExecRequest(tuple(command), cwd=cwd, timeout_seconds=timeout),
        )
        return asdict(result)

    def read_file(self, path: str) -> bytes:
        return self._backend.read_file(self._sandbox_id, path)

    def write_file(self, path: str, data: bytes) -> None:
        self._backend.write_file(self._sandbox_id, path, data)

    def list_files(self, path: str) -> list[dict]:
        return [asdict(entry) for entry in self._backend.list_files(self._sandbox_id, path)]

    def upload_asset(self, asset_ref: str) -> str:
        return self._backend.upload_asset(self._sandbox_id, asset_ref)

    def collect_artifact(self, path: str) -> dict:
        return asdict(self._backend.collect_artifact(self._sandbox_id, path))
