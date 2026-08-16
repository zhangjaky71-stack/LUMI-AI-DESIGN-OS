from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .contracts import DeepAgentInvocationContext, ResolvedSubagent
from .errors import DeepAgentBackendBoundaryError, DeepAgentModelBoundaryError


class ProfileModelProvider:
    """Resolve only LangChain models already wrapped by Model Gateway + run budget."""

    def __init__(self, resolver: Callable[[str, Any], Awaitable[Any]]) -> None:
        self.resolver = resolver

    async def model_for_root(
        self,
        *,
        model_profile: str,
        context: DeepAgentInvocationContext,
    ) -> Any:
        model = await self.resolver(model_profile, context)
        _require_model_markers(model)
        return model

    async def model_for_subagent(
        self,
        *,
        definition: ResolvedSubagent,
        context: DeepAgentInvocationContext,
    ) -> Any:
        model = await self.resolver(definition.model_profile, context)
        _require_model_markers(model)
        return model


@dataclass(slots=True)
class StaticCheckpointerProvider:
    checkpointer: Any

    async def checkpointer_for_run(self, *, context: DeepAgentInvocationContext) -> Any:
        del context
        if self.checkpointer is None:
            raise DeepAgentBackendBoundaryError("durable checkpointer is required")
        return self.checkpointer


@dataclass(slots=True)
class StaticStoreProvider:
    store: Any

    async def store_for_run(self, *, context: DeepAgentInvocationContext) -> Any:
        del context
        return self.store


def mark_model_gateway_budget_bound(model: Any) -> Any:
    _mark(model, "_lumi_model_gateway_bound", True)
    _mark(model, "_lumi_budget_meter_bound", True)
    return model


def _require_model_markers(model: Any) -> None:
    if not bool(getattr(model, "_lumi_model_gateway_bound", False)):
        raise DeepAgentModelBoundaryError("model bypasses NODE-22 Model Gateway")
    if not bool(getattr(model, "_lumi_budget_meter_bound", False)):
        raise DeepAgentModelBoundaryError("model bypasses NODE-27 run budget metering")


def _mark(obj: Any, name: str, value: Any) -> None:
    try:
        object.__setattr__(obj, name, value)
    except Exception:
        try:
            setattr(obj, name, value)
        except Exception as exc:
            raise DeepAgentModelBoundaryError(f"cannot mark trusted model: {name}") from exc
