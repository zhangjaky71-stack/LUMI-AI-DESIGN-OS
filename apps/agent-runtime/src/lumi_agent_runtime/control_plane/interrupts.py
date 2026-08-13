from __future__ import annotations

from importlib import import_module
from typing import Any
from uuid import UUID

from .contracts import InterruptKind


def approval_interrupt(
    *,
    approval_id: UUID,
    action: str,
    summary: str,
    risk: str,
    subject_ref: str | None = None,
) -> Any:
    """Create a policy-safe LangGraph interrupt payload for an existing LUMI Approval.

    The interrupt is only a pause/resume transport. Approval identity and decision remain
    authoritative in the LUMI Approval service; callers must not treat the returned resume
    value as self-authorizing.
    """
    if not action or len(action) > 128:
        raise ValueError("GRAPH_APPROVAL_ACTION_INVALID")
    if not summary or len(summary) > 1000:
        raise ValueError("GRAPH_APPROVAL_SUMMARY_INVALID")
    if not risk or len(risk) > 64:
        raise ValueError("GRAPH_APPROVAL_RISK_INVALID")
    if subject_ref is not None and len(subject_ref) > 512:
        raise ValueError("GRAPH_APPROVAL_SUBJECT_INVALID")
    payload = {
        "kind": InterruptKind.APPROVAL.value,
        "approval_id": str(approval_id),
        "action": action,
        "summary": summary,
        "risk": risk,
        "subject_ref": subject_ref,
    }
    interrupt = getattr(import_module("langgraph.types"), "interrupt")
    return interrupt(payload)


def input_interrupt(
    *,
    request_key: str,
    prompt: str,
    schema: dict[str, Any] | None = None,
) -> Any:
    """Pause for LUMI-owned user input without embedding secrets or provider credentials."""
    if not request_key or len(request_key) > 128:
        raise ValueError("GRAPH_INPUT_REQUEST_KEY_INVALID")
    if not prompt or len(prompt) > 1000:
        raise ValueError("GRAPH_INPUT_PROMPT_INVALID")
    payload = {
        "kind": InterruptKind.INPUT.value,
        "request_key": request_key,
        "prompt": prompt,
        "schema": schema or {"type": "string"},
    }
    interrupt = getattr(import_module("langgraph.types"), "interrupt")
    return interrupt(payload)
