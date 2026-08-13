from __future__ import annotations


class GraphControlPlaneError(RuntimeError):
    code = "GRAPH_CONTROL_PLANE_ERROR"


class GraphNotFoundError(GraphControlPlaneError):
    code = "GRAPH_NOT_FOUND"


class GraphDisabledError(GraphControlPlaneError):
    code = "GRAPH_DISABLED"


class GraphVersionConflictError(GraphControlPlaneError):
    code = "GRAPH_VERSION_CONFLICT"


class GraphRunConflictError(GraphControlPlaneError):
    code = "GRAPH_RUN_CONFLICT"


class GraphRunNotFoundError(GraphControlPlaneError):
    code = "GRAPH_RUN_NOT_FOUND"


class GraphRunTerminalError(GraphControlPlaneError):
    code = "GRAPH_RUN_TERMINAL"


class GraphInterruptNotFoundError(GraphControlPlaneError):
    code = "GRAPH_INTERRUPT_NOT_FOUND"


class GraphResumeDeniedError(GraphControlPlaneError):
    code = "GRAPH_RESUME_DENIED"


class GraphCheckpointRequiredError(GraphControlPlaneError):
    code = "GRAPH_CHECKPOINT_REQUIRED"


class GraphCheckpointConflictError(GraphControlPlaneError):
    code = "GRAPH_CHECKPOINT_CONFLICT"


class GraphExecutionError(GraphControlPlaneError):
    code = "GRAPH_EXECUTION_FAILED"


class GraphCancellationError(GraphControlPlaneError):
    code = "GRAPH_CANCELLATION_FAILED"
