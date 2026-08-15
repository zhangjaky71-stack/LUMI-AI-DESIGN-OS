from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


class RolloutError(RuntimeError):
    """Raised when a shadow/canary transition is unsafe or invalid."""


CANARY_STAGES = ("internal", "5", "25", "50", "100")


@dataclass(frozen=True)
class RolloutState:
    baseline_version: str
    candidate_version: str
    production_alias: str
    stage: str = "internal"
    status: str = "shadow"


def validate_shadow_plan(plan: dict[str, Any]) -> None:
    if plan.get("side_effects") is not False:
        raise RolloutError("shadow plan must disable all external side effects")
    if plan.get("destructive_tools") is not False:
        raise RolloutError("shadow plan must not invoke destructive tools")
    if plan.get("display_to_user") is not False:
        raise RolloutError("shadow candidate output must not be displayed to users")
    budget = plan.get("budget_usd")
    if not isinstance(budget, (int, float)) or isinstance(budget, bool) or not 0 < float(budget) <= 100:
        raise RolloutError("shadow budget_usd must be > 0 and <= 100")
    if plan.get("authorized_data") is not True:
        raise RolloutError("shadow plan requires authorized/de-identified input policy")


def canary_action(observation: dict[str, Any]) -> dict[str, str]:
    if observation.get("provider_failure") is True:
        return {"action": "ROLLBACK", "reason": "provider_failure"}
    if observation.get("release_gate_passed") is not True:
        return {"action": "ROLLBACK", "reason": "release_gate_not_green"}
    critical = observation.get("critical_failures", 0)
    if not isinstance(critical, (int, float)) or float(critical) != 0:
        return {"action": "ROLLBACK", "reason": "critical_failure"}
    error_ratio = observation.get("error_ratio_vs_baseline", 1.0)
    if not isinstance(error_ratio, (int, float)) or float(error_ratio) > 1.2:
        return {"action": "ROLLBACK", "reason": "error_regression"}
    cost_ratio = observation.get("cost_ratio_vs_baseline", 1.0)
    if not isinstance(cost_ratio, (int, float)) or float(cost_ratio) > 1.2:
        return {"action": "ROLLBACK", "reason": "cost_regression"}
    quality_delta = observation.get("quality_delta", 0.0)
    if not isinstance(quality_delta, (int, float)) or float(quality_delta) < -0.02:
        return {"action": "ROLLBACK", "reason": "quality_regression"}
    return {"action": "CONTINUE", "reason": "within_guardrails"}


def advance_canary(state: RolloutState, observation: dict[str, Any]) -> RolloutState:
    if state.status not in {"shadow", "canary"}:
        raise RolloutError(f"cannot advance rollout from status {state.status}")
    action = canary_action(observation)
    if action["action"] != "CONTINUE":
        raise RolloutError(f"canary requires rollback: {action['reason']}")

    try:
        index = CANARY_STAGES.index(state.stage)
    except ValueError as exc:
        raise RolloutError(f"invalid canary stage: {state.stage}") from exc
    if index == len(CANARY_STAGES) - 1:
        return replace(state, production_alias=state.candidate_version, status="promoted")
    next_stage = CANARY_STAGES[index + 1]
    return replace(state, stage=next_stage, status="canary")


def rollback(state: RolloutState, *, reason: str) -> RolloutState:
    if not reason.strip():
        raise RolloutError("rollback requires a reason")
    return replace(
        state,
        production_alias=state.baseline_version,
        status="rolled_back",
    )
