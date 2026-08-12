from __future__ import annotations

import os
from typing import Any


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
    return {
        "status": "READY",
        "suite": suite,
        "budget_usd": budget,
        "reason": "provider adapter is introduced by later benchmark/model nodes",
    }
