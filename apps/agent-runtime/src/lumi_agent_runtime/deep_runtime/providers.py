from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .contracts import (
    DeepAgentInvocationContext,
    DeepSubagentDefinition,
    SubagentInvocationContext,
)
from .errors import (
    DeepAgentBackendBoundaryError,
    DeepAgentModelBoundaryError,
)


class ProfileModelProvider:
    """Trusted profile resolver for LangChain models already bound to NODE-22."""

    def __init__(
        self,
        resolver: Callable[[str, Any], Awaitable[Any]],
    ) -> None:
        self.resolver = resolver

    async def model_for_root(
        self,
        *,
        model_profile: str,
        context: DeepAgentInvocationContext,
    ) -> Any:
        model = await self.resolver(model_profile, context)
        _require_model_marker(model)
        return model

    async def model_for_subagent(
        self,
        *,
        definition: DeepSubagentDefinition,
        context: SubagentInvocationContext,
    ) -> Any:
        model = await self.resolver(definition.model_profile, context)
        _require_model_marker(model)
        return model


class TrustedBackendProvider:
    def __init__(
        self,
        resolver: Callable[[DeepAgentInvocationContext, bool], Awaitable[Any]],
    ) -> None:
        self.resolver = resolver

    async def backend_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
        virtual_files_enabled: bool,
    ) -> Any:
        backend = await self.resolver(context, virtual_files_enabled)
        if not bool(getattr(backend, "_lumi_backend_bound", False)):
            raise DeepAgentBackendBoundaryError("backend resolver returned untrusted backend")
        return backend


@dataclass(slots=True)
class StaticCheckpointerProvider:
    checkpointer: Any

    async def checkpointer_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
    ) -> Any:
        del context
        if self.checkpointer is None:
            raise DeepAgentBackendBoundaryError("durable checkpointer is required")
        return self.checkpointer


@dataclass(slots=True)
class StaticStoreProvider:
    store: Any

    async def store_for_run(
        self,
        *,
        context: DeepAgentInvocationContext,
    ) -> Any:
        del context
        return self.store


def mark_model_gateway_bound(model: Any) -> Any:
    _mark(model, "_lumi_model_gateway_bound", True)
    return model


def mark_backend_bound(backend: Any) -> Any:
    _mark(backend, "_lumi_backend_bound", True)
    return backend


def _require_model_marker(model: Any) -> None:
    if not bool(getattr(model, "_lumi_model_gateway_bound", False)):
        raise DeepAgentModelBoundaryError("model is not bound to NODE-22 Model Gateway")


def _mark(obj: Any, name: str, value: Any) -> None:
    try:
        object.__setattr__(obj, name, value)
    except Exception:
        try:
            setattr(obj, name, value)
        except Exception as exc:
            raise DeepAgentBackendBoundaryError(f"cannot mark trusted object: {name}") from exc
