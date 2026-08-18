from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SLODefinition:
    key: str
    target: float
    window_days: int
    description: str

    def __post_init__(self) -> None:
        if not self.key or len(self.key) > 120:
            raise ValueError("OBSERVABILITY_SLO_KEY_INVALID")
        if not 0.0 < self.target <= 1.0:
            raise ValueError("OBSERVABILITY_SLO_TARGET_INVALID")
        if self.window_days < 1 or self.window_days > 365:
            raise ValueError("OBSERVABILITY_SLO_WINDOW_INVALID")
        if not self.description.strip():
            raise ValueError("OBSERVABILITY_SLO_DESCRIPTION_REQUIRED")


@dataclass(frozen=True, slots=True)
class ErrorBudgetSnapshot:
    slo_key: str
    target: float
    total_events: int
    bad_events: int
    allowed_bad_events: float
    remaining_bad_events: float
    budget_remaining_ratio: float
    burn_ratio: float


def evaluate_error_budget(
    definition: SLODefinition,
    *,
    total_events: int,
    bad_events: int,
) -> ErrorBudgetSnapshot:
    if total_events < 0 or bad_events < 0 or bad_events > total_events:
        raise ValueError("OBSERVABILITY_ERROR_BUDGET_COUNTS_INVALID")
    budget_fraction = 1.0 - definition.target
    allowed_bad = total_events * budget_fraction
    if total_events == 0:
        remaining_ratio = 1.0
        burn_ratio = 0.0
    elif allowed_bad == 0:
        remaining_ratio = 1.0 if bad_events == 0 else 0.0
        burn_ratio = 0.0 if bad_events == 0 else float("inf")
    else:
        remaining = max(0.0, allowed_bad - bad_events)
        remaining_ratio = remaining / allowed_bad
        burn_ratio = bad_events / allowed_bad
    return ErrorBudgetSnapshot(
        slo_key=definition.key,
        target=definition.target,
        total_events=total_events,
        bad_events=bad_events,
        allowed_bad_events=allowed_bad,
        remaining_bad_events=max(0.0, allowed_bad - bad_events),
        budget_remaining_ratio=remaining_ratio,
        burn_ratio=burn_ratio,
    )


CORE_API_AVAILABILITY = SLODefinition(
    key="core_api.availability",
    target=0.999,
    window_days=30,
    description="Monthly availability for core non-long-running API requests.",
)
NO_DUPLICATE_PAID_SIDE_EFFECTS = SLODefinition(
    key="paid_side_effects.no_duplicate",
    target=1.0,
    window_days=30,
    description="Paid side effects must not execute more than once for one idempotent operation.",
)
