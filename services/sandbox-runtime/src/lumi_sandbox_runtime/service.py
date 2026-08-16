from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .audit import AuditSink
from .backend import SandboxBackend
from .models import (
    AssetInputRef,
    AuditAction,
    CollectedArtifact,
    ExecResult,
    FileEntry,
    ResourceUsage,
    SandboxAccessContext,
    SandboxAuditEvent,
    SandboxCommand,
    SandboxHandle,
    SandboxSpec,
)
from .redaction import SecretRedactor

T = TypeVar("T")


class SandboxAccessDenied(PermissionError):
    code = "SANDBOX_ACCESS_DENIED"


class SandboxRuntimeService:
    def __init__(
        self,
        backend: SandboxBackend,
        audit: AuditSink,
        *,
        redactor: SecretRedactor | None = None,
    ) -> None:
        self.backend = backend
        self.audit = audit
        self.redactor = redactor or SecretRedactor()
        self._handles: dict[str, SandboxHandle] = {}
        self._specs: dict[str, SandboxSpec] = {}
        self._expiry_tasks: dict[str, asyncio.Task[None]] = {}

    async def create(self, spec: SandboxSpec, *, context: SandboxAccessContext) -> SandboxHandle:
        if spec.organization_id != context.organization_id or spec.agent_run_id != context.agent_run_id:
            raise SandboxAccessDenied("sandbox spec must match request organization and agent run")
        handle = await self.backend.create(spec)
        self._handles[handle.sandbox_id] = handle
        self._specs[handle.sandbox_id] = spec
        await self._emit(handle.sandbox_id, AuditAction.CREATE)
        lifetime = max(1, min(spec.ttl_seconds, spec.timeout_seconds))
        self._expiry_tasks[handle.sandbox_id] = asyncio.create_task(
            self._expire(handle.sandbox_id, context, lifetime)
        )
        return handle

    async def exec(
        self,
        sandbox_id: str,
        command: SandboxCommand,
        *,
        context: SandboxAccessContext,
    ) -> ExecResult:
        self._authorize(sandbox_id, context)
        try:
            result = await self.backend.exec(sandbox_id, command)
        except Exception as exc:
            await self._emit(
                sandbox_id,
                AuditAction.SECURITY_DENY,
                command=self.redactor.redact_argv(command.argv),
                detail={"error": self.redactor.redact(str(exc))[:1000]},
            )
            raise
        await self._emit(
            sandbox_id,
            AuditAction.EXEC,
            command=self.redactor.redact_argv(command.argv),
            exit_code=result.exit_code,
            usage=result.usage,
            detail={"timed_out": result.timed_out},
        )
        return result

    async def read_file(
        self, sandbox_id: str, path: str, *, context: SandboxAccessContext
    ) -> bytes:
        self._authorize(sandbox_id, context)
        return await self._audited_path_call(
            sandbox_id,
            AuditAction.READ_FILE,
            path,
            lambda: self.backend.read_file(sandbox_id, path),
        )

    async def write_file(
        self,
        sandbox_id: str,
        path: str,
        content: bytes,
        *,
        context: SandboxAccessContext,
    ) -> None:
        self._authorize(sandbox_id, context)
        await self._audited_path_call(
            sandbox_id,
            AuditAction.WRITE_FILE,
            path,
            lambda: self.backend.write_file(sandbox_id, path, content),
        )

    async def list_files(
        self, sandbox_id: str, path: str, *, context: SandboxAccessContext
    ) -> list[FileEntry]:
        self._authorize(sandbox_id, context)
        return await self._audited_path_call(
            sandbox_id,
            AuditAction.LIST_FILES,
            path,
            lambda: self.backend.list_files(sandbox_id, path),
        )

    async def upload_asset(
        self,
        sandbox_id: str,
        asset: AssetInputRef,
        *,
        context: SandboxAccessContext,
    ) -> str:
        self._authorize(sandbox_id, context)
        try:
            path = await self.backend.upload_asset(sandbox_id, asset)
        except Exception as exc:
            await self._emit(
                sandbox_id,
                AuditAction.SECURITY_DENY,
                path=f"input/{asset.filename}",
                detail={"error": self.redactor.redact(str(exc))[:1000]},
            )
            raise
        await self._emit(
            sandbox_id,
            AuditAction.UPLOAD_ASSET,
            path=path,
            detail={"asset_id": str(asset.asset_id), "size": len(asset.content)},
        )
        return path

    async def collect_artifact(
        self,
        sandbox_id: str,
        path: str,
        *,
        context: SandboxAccessContext,
    ) -> CollectedArtifact:
        self._authorize(sandbox_id, context)
        try:
            artifact = await self.backend.collect_artifact(sandbox_id, path)
        except Exception as exc:
            await self._emit(
                sandbox_id,
                AuditAction.SECURITY_DENY,
                path=path,
                detail={"error": self.redactor.redact(str(exc))[:1000]},
            )
            raise
        await self._emit(
            sandbox_id,
            AuditAction.COLLECT_ARTIFACT,
            path=artifact.path,
            result_ref=artifact.storage_ref,
            detail={
                "sha256": artifact.sha256,
                "size": artifact.size,
                "detected_mime": artifact.detected_mime,
            },
        )
        return artifact

    async def terminate(self, sandbox_id: str, *, context: SandboxAccessContext) -> None:
        self._authorize(sandbox_id, context)
        await self.backend.terminate(sandbox_id)
        await self._emit(sandbox_id, AuditAction.TERMINATE)
        self._handles.pop(sandbox_id, None)
        self._specs.pop(sandbox_id, None)
        task = self._expiry_tasks.pop(sandbox_id, None)
        current = asyncio.current_task()
        if task is not None and task is not current:
            task.cancel()

    def _authorize(self, sandbox_id: str, context: SandboxAccessContext) -> SandboxHandle:
        handle = self._handles.get(sandbox_id)
        if handle is None:
            raise SandboxAccessDenied("sandbox not found")
        if handle.organization_id != context.organization_id or handle.agent_run_id != context.agent_run_id:
            raise SandboxAccessDenied("sandbox not found")
        return handle

    async def _audited_path_call(
        self,
        sandbox_id: str,
        action: AuditAction,
        path: str,
        call: Callable[[], Awaitable[T]],
    ) -> T:
        try:
            result = await call()
        except Exception as exc:
            await self._emit(
                sandbox_id,
                AuditAction.SECURITY_DENY,
                path=path,
                detail={"error": self.redactor.redact(str(exc))[:1000]},
            )
            raise
        await self._emit(sandbox_id, action, path=path)
        return result

    async def _expire(
        self,
        sandbox_id: str,
        context: SandboxAccessContext,
        lifetime_seconds: int,
    ) -> None:
        try:
            await asyncio.sleep(lifetime_seconds)
            if sandbox_id in self._handles:
                await self.terminate(sandbox_id, context=context)
        except (asyncio.CancelledError, SandboxAccessDenied):
            return

    async def _emit(
        self,
        sandbox_id: str,
        action: AuditAction,
        *,
        command: tuple[str, ...] | None = None,
        exit_code: int | None = None,
        usage: ResourceUsage | None = None,
        path: str | None = None,
        result_ref: str | None = None,
        detail: dict[str, object] | None = None,
    ) -> None:
        handle = self._handles.get(sandbox_id)
        spec = self._specs.get(sandbox_id)
        if handle is None or spec is None:
            return
        await self.audit.emit(
            SandboxAuditEvent(
                sandbox_id=sandbox_id,
                organization_id=handle.organization_id,
                agent_run_id=handle.agent_run_id,
                action=action,
                image_version=handle.image_version,
                network_policy=spec.network_policy,
                command=command,
                exit_code=exit_code,
                usage=usage,
                path=path,
                result_ref=result_ref,
                detail=dict(detail or {}),
            )
        )
