class ControlPlaneError(RuntimeError):
    code = "GRAPH_CONTROL_PLANE_ERROR"


class GraphNotFound(ControlPlaneError):
    code = "GRAPH_VERSION_NOT_AVAILABLE"


class GraphVersionMismatch(ControlPlaneError):
    code = "GRAPH_VERSION_MISMATCH"


class RunNotFound(ControlPlaneError):
    code = "AGENT_RUN_NOT_FOUND"


class RunConflict(ControlPlaneError):
    code = "AGENT_RUN_CONTROL_CONFLICT"


class ResumeDenied(ControlPlaneError):
    code = "AGENT_RUN_RESUME_DENIED"


class ResumeVersionConflict(ControlPlaneError):
    code = "AGENT_RUN_RESUME_VERSION_CONFLICT"


class CheckpointUnavailable(ControlPlaneError):
    code = "LANGGRAPH_DURABLE_CHECKPOINT_UNAVAILABLE"


class GraphExecutionFailed(ControlPlaneError):
    code = "LANGGRAPH_EXECUTION_FAILED"
