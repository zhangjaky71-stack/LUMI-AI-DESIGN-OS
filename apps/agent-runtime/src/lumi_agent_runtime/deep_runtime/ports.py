from __future__ import annotations

from typing import Any, Protocol

from .contracts import (
    DeepAgentInvocationContext,
    DeepSubagentDefinition,
    SubagentInvocationContext,
)


class DeepAgentModelProvider(Protocol):
    """Returns a LangChain-compatible chat model backed by NODE-22 Model Gateway."""

    async def model_for_root(
        self,
        *,
        model_profile: str,
        context: DeepAgentInvocationContext,
    ) -> Any: ...

    async def model_for_subagent(
        self,
        *,
        definition: DeepSubagentDefinition,
        context: SubagentInvocationContext,
    ) -> Any: ...


class DeepAgentToolProvider(Protocol):
    """Returns LangChain-compatible tools that execute only through NODE-25."""

    async def tools_for_root(
        self,
        *,
        context: DeepAgentInvocationContext,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]: ...

    async def tools_for_subagent(
        self,
        *,
        context: SubagentInvocationContext,
        allowed_tools: tuple[str, ...],
    ) -> tuple[Any, ...]: ...


class DeepAgentBackendProvider(Protocol):
    """Creates the Deep Agents virtual-file/backend object from LUMI trusted services."""

    async def backend_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
        virtual_files_enabled: bool,
    ) -> Any: ...


class DeepAgentCheckpointerProvider(Protocol):
    async def checkpointer_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
    ) -> Any: ...


class DeepAgentStoreProvider(Protocol):
    async def store_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
    ) -> Any: ...
