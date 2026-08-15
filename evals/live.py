from __future__ import annotations

import os
from typing import Any

DEFAULT_MAX_LIVE_EVAL_BUDGET_USD = 25.0


def live_preflight(suite: str) -> dict[str, Any]:
    enabled = os.getenv("LUMI_LIVE_EVAL_ENABLED") == "1"
    api_key = os.getenv("LUMI_LIVE_EVAL_API_KEY")
    budget_raw = os.getenv("LUMI_LIVE_EVAL_BUDGET_USD")
    if not enabled:
        return {
            "status": "SKIPPED",
            "suite": suite,
            "reason": "LUMI_LIVE_EVAL_ENABLED is not 1",
        }
    if not api_key:
        return {
            "status": "SKIPPED",
            "suite": suite,
            "reason": "LUMI_LIVE_EVAL_API_KEY is not configured",
        }
    if budget_raw is None:
        return {
            "status": "SKIPPED",
            "suite": suite,
            "reason": "LUMI_LIVE_EVAL_BUDGET_USD is not configured",
        }
    try:
        budget = float(budget_raw)
    except ValueError:
        return {"status": "SKIPPED", "suite": suite, "reason": "live eval budget is invalid"}
    if budget <= 0:
        return {"status": "SKIPPED", "suite": suite, "reason": "live eval budget must be > 0"}

    max_raw = os.getenv("LUMI_LIVE_EVAL_MAX_BUDGET_USD", str(DEFAULT_MAX_LIVE_EVAL_BUDGET_USD))
    try:
        max_budget = float(max_raw)
    except ValueError:
        return {"status": "SKIPPED", "suite": suite, "reason": "live eval max budget is invalid"}
    if max_budget <= 0 or budget > max_budget:
        return {
            "status": "SKIPPED",
            "suite": suite,
            "reason": f"live eval budget exceeds configured maximum {max_budget:g}",
        }

    if os.getenv("LUMI_LIVE_EVAL_SUITE_ACK") != suite:
        return {
            "status": "SKIPPED",
            "suite": suite,
            "reason": "LUMI_LIVE_EVAL_SUITE_ACK must exactly match the requested suite",
        }
    if os.getenv("LUMI_LIVE_EVAL_SIDE_EFFECT_MODE") != "none":
        return {
            "status": "SKIPPED",
            "suite": suite,
            "reason": "LUMI_LIVE_EVAL_SIDE_EFFECT_MODE must be none",
        }
    return {
        "status": "READY",
        "suite": suite,
        "budget_usd": budget,
        "max_budget_usd": max_budget,
        "side_effect_mode": "none",
        "reason": "live provider evaluation is explicitly authorized for this suite and budget",
    }
