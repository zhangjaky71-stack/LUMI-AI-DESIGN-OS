from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")
_ALLOWED_TRACING_MODES = frozenset({"langsmith", "otel", "hybrid"})


@dataclass(frozen=True, slots=True)
class LangSmithPolicy:
    enabled: bool
    project: str
    tracing_mode: str
    hide_inputs: bool
    hide_outputs: bool
    hide_metadata: bool

    @classmethod
    def from_environment(cls) -> LangSmithPolicy:
        mode = os.environ.get("LANGSMITH_TRACING_MODE", "otel").strip().lower()
        if mode not in _ALLOWED_TRACING_MODES:
            raise ValueError("LANGSMITH_TRACING_MODE_INVALID")
        return cls(
            enabled=_env_bool("LANGSMITH_TRACING", default=False),
            project=os.environ.get("LANGSMITH_PROJECT", "lumi-local").strip() or "lumi-local",
            tracing_mode=mode,
            hide_inputs=_env_bool("LANGSMITH_HIDE_INPUTS", default=True),
            hide_outputs=_env_bool("LANGSMITH_HIDE_OUTPUTS", default=True),
            hide_metadata=_env_bool("LANGSMITH_HIDE_METADATA", default=False),
        )

    def validate_production_privacy(self) -> None:
        if self.enabled and (not self.hide_inputs or not self.hide_outputs):
            raise ValueError("LANGSMITH_PRODUCTION_CONTENT_CAPTURE_FORBIDDEN")


@dataclass(frozen=True, slots=True)
class AgentTraceRefs:
    environment: str
    agent_run_id: str
    organization_id: str
    project_id: str | None = None
    task_id: str | None = None
    operation_id: str | None = None
    trace_id: str | None = None

    def safe_metadata(self) -> dict[str, str]:
        values = {
            "environment": self.environment,
            "agent_run_id": self.agent_run_id,
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "operation_id": self.operation_id,
            "trace_id": self.trace_id,
        }
        return {key: value for key, value in values.items() if value}


def best_effort_trace(observer: Callable[[], Any] | None) -> bool:
    """Execute telemetry without allowing an observability outage to fail the run."""
    if observer is None:
        return False
    try:
        observer()
        return True
    except Exception:
        return False


def best_effort_observed_call(
    operation: Callable[[], _T],
    *,
    before: Callable[[], Any] | None = None,
    after: Callable[[], Any] | None = None,
) -> _T:
    best_effort_trace(before)
    try:
        return operation()
    finally:
        best_effort_trace(after)


def langsmith_environment(policy: LangSmithPolicy) -> dict[str, str]:
    """Return the non-secret runtime settings expected by LangChain/LangSmith.

    API keys/endpoints are deliberately excluded; deployment injects credentials from
    the secret manager. Inputs/outputs are hidden by default to avoid prompt/content
    capture unless an explicit privacy review permits a narrower policy.
    """

    return {
        "LANGSMITH_TRACING": "true" if policy.enabled else "false",
        "LANGSMITH_PROJECT": policy.project,
        "LANGSMITH_TRACING_MODE": policy.tracing_mode,
        "LANGSMITH_HIDE_INPUTS": "true" if policy.hide_inputs else "false",
        "LANGSMITH_HIDE_OUTPUTS": "true" if policy.hide_outputs else "false",
        "LANGSMITH_HIDE_METADATA": "true" if policy.hide_metadata else "false",
    }


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name}_INVALID_BOOLEAN")
