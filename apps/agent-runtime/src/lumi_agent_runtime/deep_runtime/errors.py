from __future__ import annotations


class DeepAgentRuntimeError(RuntimeError):
    code = "DEEP_AGENT_RUNTIME_ERROR"


class DeepAgentNotFoundError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_NOT_FOUND"


class DeepAgentDisabledError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_DISABLED"


class DeepAgentVersionConflictError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_VERSION_CONFLICT"


class DeepAgentToolScopeError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_TOOL_SCOPE_DENIED"


class DeepAgentDelegationDeniedError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_DELEGATION_DENIED"


class DeepAgentDelegationLimitError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_DELEGATION_LIMIT"


class DeepAgentModelBoundaryError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_MODEL_BOUNDARY_INVALID"


class DeepAgentBackendBoundaryError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_BACKEND_BOUNDARY_INVALID"


class DeepAgentFactoryError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_FACTORY_ERROR"
