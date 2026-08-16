from __future__ import annotations

import posixpath
from dataclasses import dataclass

from .contracts import PermissionScope
from .errors import DeepAgentFilesystemError

_READ_ONLY_ROOTS = ("/workspace/input", "/skills")
_WRITABLE_ROOTS = ("/workspace/work", "/workspace/output")


@dataclass(frozen=True, slots=True)
class ScopedWorkspacePolicy:
    permissions: PermissionScope

    def normalize(self, path: str) -> str:
        if not isinstance(path, str) or not path.startswith("/"):
            raise DeepAgentFilesystemError("virtual path must be absolute")
        normalized = posixpath.normpath(path)
        if normalized == "/" or "\x00" in normalized:
            raise DeepAgentFilesystemError("virtual path is not allowed")
        if path.endswith("/..") or "/../" in path:
            raise DeepAgentFilesystemError("path traversal is forbidden")
        if not self._known_root(normalized):
            raise DeepAgentFilesystemError(f"path outside scoped workspace: {normalized}")
        return normalized

    def authorize_read(self, path: str) -> str:
        normalized = self.normalize(path)
        if normalized.startswith("/memory/") and not self.permissions.memory_read_scopes:
            raise DeepAgentFilesystemError("memory read scope is empty")
        return normalized

    def authorize_write(self, path: str) -> str:
        normalized = self.normalize(path)
        if _under(normalized, _READ_ONLY_ROOTS):
            raise DeepAgentFilesystemError(f"read-only virtual path: {normalized}")
        if _under(normalized, _WRITABLE_ROOTS):
            return normalized
        if normalized.startswith("/memory/"):
            if not self.permissions.memory_write_scopes:
                raise DeepAgentFilesystemError("memory write scope is empty")
            return normalized
        raise DeepAgentFilesystemError(f"write not allowed: {normalized}")

    def authorize_execute(self) -> None:
        if not self.permissions.sandbox_execute:
            raise DeepAgentFilesystemError("sandbox execute permission not granted")

    @staticmethod
    def _known_root(path: str) -> bool:
        roots = _READ_ONLY_ROOTS + _WRITABLE_ROOTS + ("/memory",)
        return any(path == root or path.startswith(root + "/") for root in roots)


def assert_trusted_backend(backend: object, policy: ScopedWorkspacePolicy) -> None:
    if not bool(getattr(backend, "_lumi_backend_bound", False)):
        raise DeepAgentFilesystemError("backend is not bound to LUMI")
    bound_hash = getattr(backend, "_lumi_permission_scope_hash", None)
    expected = _permission_hash(policy.permissions)
    if bound_hash != expected:
        raise DeepAgentFilesystemError("backend permission scope does not match invocation")
    if policy.permissions.sandbox_execute and not bool(
        getattr(backend, "_lumi_sandbox_execute_bound", False)
    ):
        raise DeepAgentFilesystemError("execute permission lacks SandboxBackend binding")
    identity = f"{type(backend).__module__}.{type(backend).__name__}".casefold()
    for marker in ("filesystembackend", "localshell", "local_shell", "dockerbackend"):
        if marker in identity:
            raise DeepAgentFilesystemError(f"host-local backend is forbidden: {identity}")


def mark_trusted_backend(
    backend: object,
    *,
    permissions: PermissionScope,
    sandbox_execute_bound: bool,
) -> object:
    _mark(backend, "_lumi_backend_bound", True)
    _mark(backend, "_lumi_permission_scope_hash", _permission_hash(permissions))
    _mark(backend, "_lumi_sandbox_execute_bound", bool(sandbox_execute_bound))
    return backend


def _under(path: str, roots: tuple[str, ...]) -> bool:
    return any(path == root or path.startswith(root + "/") for root in roots)


def _permission_hash(scope: PermissionScope) -> str:
    import hashlib
    import json

    payload = {
        "tools": scope.allowed_tools,
        "sandbox_execute": scope.sandbox_execute,
        "memory_read": scope.memory_read_scopes,
        "memory_write": scope.memory_write_scopes,
        "subagents": scope.allowed_subagents,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mark(obj: object, name: str, value: object) -> None:
    try:
        object.__setattr__(obj, name, value)
    except Exception:
        try:
            setattr(obj, name, value)
        except Exception as exc:
            raise DeepAgentFilesystemError(f"cannot mark trusted backend: {name}") from exc
