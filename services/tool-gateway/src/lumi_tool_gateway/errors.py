from __future__ import annotations


class ToolGatewayError(RuntimeError):
    code = "TOOL_GATEWAY_ERROR"


class ToolNotFoundError(ToolGatewayError):
    code = "TOOL_NOT_FOUND"


class ToolVersionError(ToolGatewayError):
    code = "TOOL_VERSION_NOT_FOUND"


class ToolDisabledError(ToolGatewayError):
    code = "TOOL_DISABLED"


class ToolPermissionDeniedError(ToolGatewayError):
    code = "TOOL_PERMISSION_DENIED"


class ToolApprovalRequiredError(ToolGatewayError):
    code = "TOOL_APPROVAL_REQUIRED"


class ToolApprovalDeniedError(ToolGatewayError):
    code = "TOOL_APPROVAL_DENIED"


class ToolInputValidationError(ToolGatewayError):
    code = "TOOL_INPUT_SCHEMA_INVALID"


class ToolOutputValidationError(ToolGatewayError):
    code = "TOOL_OUTPUT_SCHEMA_INVALID"


class ToolTimeoutError(ToolGatewayError):
    code = "TOOL_TIMEOUT"


class ToolAdapterExecutionError(ToolGatewayError):
    code = "TOOL_ADAPTER_EXECUTION_ERROR"


class ToolInternalError(ToolGatewayError):
    code = "TOOL_INTERNAL_ERROR"


class ToolIdempotencyRequiredError(ToolGatewayError):
    code = "TOOL_IDEMPOTENCY_KEY_REQUIRED"


class ToolSideEffectGuardRequiredError(ToolGatewayError):
    code = "TOOL_SIDE_EFFECT_GUARD_REQUIRED"


class ToolOutputOffloadRequiredError(ToolGatewayError):
    code = "TOOL_OUTPUT_OFFLOAD_REQUIRED"


class ToolSSRFBlockedError(ToolGatewayError):
    code = "TOOL_SSRF_BLOCKED"


class ToolRedirectLimitError(ToolGatewayError):
    code = "TOOL_REDIRECT_LIMIT"


class ToolResponseTooLargeError(ToolGatewayError):
    code = "TOOL_RESPONSE_TOO_LARGE"


class ToolUnsupportedContentTypeError(ToolGatewayError):
    code = "TOOL_CONTENT_TYPE_NOT_ALLOWED"
