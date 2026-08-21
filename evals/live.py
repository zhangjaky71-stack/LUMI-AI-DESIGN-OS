from __future__ import annotations

import os
from typing import Any

DEFAULT_MAX_LIVE_EVAL_BUDGET_USD = 25.0
AUTHORIZATION_ONLY_MODE = "authorization-only"


def live_preflight(suite: str) -> dict[str, Any]:
    enabled = os.getenv("LUMI_LIVE_EVAL_ENABLED") == "1"
    preflight_mode = os.getenv("LUMI_LIVE_EVAL_PREFLIGHT_MODE")
    budget_raw = os.getenv("LUMI_LIVE_EVAL_BUDGET_USD")
    if not enabled:
        return {
            "status": "SKIPPED",
            "suite": suite,
            "reason": "LUMI_LIVE_EVAL_ENABLED is not 1",
        }
    if preflight_mode != AUTHORIZATION_ONLY_MODE:
        return {
            "status": "SKIPPED",
            "suite": suite,
            "reason": f"LUMI_LIVE_EVAL_PREFLIGHT_MODE must be {AUTHORIZATION_ONLY_MODE}",
        }
    if os.getenv("LUMI_LIVE_EVAL_API_KEY"):
        return {
            "status": "SKIPPED",
            "suite": suite,
            "reason": "provider credentials must not be exposed to authorization-only preflight",
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
        "preflight_mode": AUTHORIZATION_ONLY_MODE,
        "budget_usd": budget,
        "max_budget_usd": max_budget,
        "side_effect_mode": "none",
        "credential_check": "NOT_PERFORMED",
        "network_execution": False,
        "reason": (
            "live-provider execution parameters are authorized; provider credentials are deliberately "
            "not exposed or validated by this preflight"
        ),
    }
