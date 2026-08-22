from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .contracts import (
    DeepAgentDefinition,
    DeepAgentInvocationContext,
    DeepSubagentDefinition,
    DelegationLimits,
    DelegationUsage,
    SubagentInvocationContext,
)
from .errors import DeepAgentRuntimeError

if TYPE_CHECKING:
    from .control_plane import (
        DeepAgentControlPlaneBundle,
        DeepAgentControlPlaneCompiler,
    )
    from .factory import CompiledDeepAgent
    from .model_gateway_chat import HttpProfileModelProvider, ModelGatewayChatModel
    from .node25_adapter import Node25ToolGatewayInvoker, StaticToolDefinitionReader
    from .ports import (
        DeepAgentBackendProvider,
        DeepAgentCheckpointerProvider,
        DeepAgentModelProvider,
        DeepAgentStoreProvider,
        DeepAgentToolProvider,
    )
    from .providers import (
        ProfileModelProvider,
        StaticCheckpointerProvider,
        StaticStoreProvider,
        TrustedBackendProvider,
    )
    from .registry import DeepAgentRegistry
    from .runtime_factory import BoundedDeepAgentRuntimeFactory, HostedDeepAgentRuntimeFactory
    from .tooling import BoundToolDefinition, LumiToolGatewayProvider

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "DeepAgentControlPlaneBundle": (".control_plane", "DeepAgentControlPlaneBundle"),
    "DeepAgentControlPlaneCompiler": (".control_plane", "DeepAgentControlPlaneCompiler"),
    "CompiledDeepAgent": (".factory", "CompiledDeepAgent"),
    "HttpProfileModelProvider": (".model_gateway_chat", "HttpProfileModelProvider"),
    "ModelGatewayChatModel": (".model_gateway_chat", "ModelGatewayChatModel"),
    "Node25ToolGatewayInvoker": (".node25_adapter", "Node25ToolGatewayInvoker"),
    "StaticToolDefinitionReader": (".node25_adapter", "StaticToolDefinitionReader"),
    "DeepAgentBackendProvider": (".ports", "DeepAgentBackendProvider"),
    "DeepAgentCheckpointerProvider": (".ports", "DeepAgentCheckpointerProvider"),
    "DeepAgentModelProvider": (".ports", "DeepAgentModelProvider"),
    "DeepAgentStoreProvider": (".ports", "DeepAgentStoreProvider"),
    "DeepAgentToolProvider": (".ports", "DeepAgentToolProvider"),
    "ProfileModelProvider": (".providers", "ProfileModelProvider"),
    "StaticCheckpointerProvider": (".providers", "StaticCheckpointerProvider"),
    "StaticStoreProvider": (".providers", "StaticStoreProvider"),
    "TrustedBackendProvider": (".providers", "TrustedBackendProvider"),
    "mark_backend_bound": (".providers", "mark_backend_bound"),
    "mark_model_gateway_bound": (".providers", "mark_model_gateway_bound"),
    "DeepAgentRegistry": (".registry", "DeepAgentRegistry"),
    "BoundedDeepAgentRuntimeFactory": (".runtime_factory", "BoundedDeepAgentRuntimeFactory"),
    "HostedDeepAgentRuntimeFactory": (".runtime_factory", "HostedDeepAgentRuntimeFactory"),
    "BoundToolDefinition": (".tooling", "BoundToolDefinition"),
    "LumiToolGatewayProvider": (".tooling", "LumiToolGatewayProvider"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


__all__ = [
    "BoundToolDefinition",
    "BoundedDeepAgentRuntimeFactory",
    "CompiledDeepAgent",
    "DeepAgentBackendProvider",
    "DeepAgentCheckpointerProvider",
    "DeepAgentControlPlaneBundle",
    "DeepAgentControlPlaneCompiler",
    "DeepAgentDefinition",
    "DeepAgentInvocationContext",
    "DeepAgentModelProvider",
    "DeepAgentRegistry",
    "DeepAgentRuntimeError",
    "DeepAgentStoreProvider",
    "DeepAgentToolProvider",
    "DeepSubagentDefinition",
    "DelegationLimits",
    "DelegationUsage",
    "HostedDeepAgentRuntimeFactory",
    "HttpProfileModelProvider",
    "LumiToolGatewayProvider",
    "ModelGatewayChatModel",
    "Node25ToolGatewayInvoker",
    "ProfileModelProvider",
    "StaticCheckpointerProvider",
    "StaticStoreProvider",
    "StaticToolDefinitionReader",
    "SubagentInvocationContext",
    "TrustedBackendProvider",
    "mark_backend_bound",
    "mark_model_gateway_bound",
]
