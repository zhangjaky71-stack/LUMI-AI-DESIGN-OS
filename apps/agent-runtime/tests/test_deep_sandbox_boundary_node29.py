from __future__ import annotations

from types import SimpleNamespace

import pytest

from lumi_agent_runtime.deep_runtime.contracts import PermissionScope
from lumi_agent_runtime.deep_runtime.errors import DeepAgentFilesystemError
from lumi_agent_runtime.deep_runtime.filesystem import (
    ScopedWorkspacePolicy,
    assert_trusted_backend,
    mark_trusted_backend,
)


class ExecuteBackend:
    def execute(self, command: str):
        return command


class AsyncExecuteBackend:
    async def aexecute(self, command: str):
        return command


def test_backend_cannot_expose_execute_without_permission() -> None:
    scope = PermissionScope(allowed_tools=())
    backend = mark_trusted_backend(
        ExecuteBackend(),
        permissions=scope,
        sandbox_execute_bound=False,
    )
    with pytest.raises(DeepAgentFilesystemError, match="without granted permission"):
        assert_trusted_backend(backend, ScopedWorkspacePolicy(scope))


def test_execute_permission_requires_real_sandbox_execute_binding() -> None:
    scope = PermissionScope(allowed_tools=(), sandbox_execute=True)
    backend = mark_trusted_backend(
        SimpleNamespace(),
        permissions=scope,
        sandbox_execute_bound=True,
    )
    with pytest.raises(DeepAgentFilesystemError, match="lacks SandboxBackend"):
        assert_trusted_backend(backend, ScopedWorkspacePolicy(scope))

    bound = mark_trusted_backend(
        AsyncExecuteBackend(),
        permissions=scope,
        sandbox_execute_bound=True,
    )
    assert_trusted_backend(bound, ScopedWorkspacePolicy(scope))
