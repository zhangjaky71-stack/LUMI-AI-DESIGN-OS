from __future__ import annotations


class DeepAgentRuntimeError(RuntimeError):
    code = "DEEP_AGENT_RUNTIME_ERROR"


class DeepAgentConfigurationError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_CONFIGURATION_INVALID"


class DeepAgentPermissionError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_PERMISSION_DENIED"


class DeepAgentToolScopeError(DeepAgentPermissionError):
    code = "DEEP_AGENT_TOOL_SCOPE_DENIED"


class DeepAgentDelegationDeniedError(DeepAgentPermissionError):
    code = "DEEP_AGENT_DELEGATION_DENIED"


class DeepAgentMemoryScopeError(DeepAgentPermissionError):
    code = "DEEP_AGENT_MEMORY_SCOPE_DENIED"


class DeepAgentFilesystemError(DeepAgentPermissionError):
    code = "DEEP_AGENT_FILESYSTEM_DENIED"


class DeepAgentModelBoundaryError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_MODEL_BOUNDARY_INVALID"


class DeepAgentBackendBoundaryError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_BACKEND_BOUNDARY_INVALID"


class DeepAgentBudgetExceeded(DeepAgentRuntimeError):
    code = "DEEP_AGENT_BUDGET_EXCEEDED"


class DeepAgentStructuredOutputError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_STRUCTURED_OUTPUT_INVALID"


class DeepAgentFactoryError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_FACTORY_ERROR"


class DeepAgentExecutionError(DeepAgentRuntimeError):
    code = "DEEP_AGENT_EXECUTION_ERROR"
