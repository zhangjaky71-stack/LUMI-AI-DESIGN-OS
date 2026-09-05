from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


class ProjectSettingsError(ValueError):
    pass


_ALLOWED_KEYS = {
    "default_locale",
    "timezone",
    "cost_budget_default",
    "quality_profile",
    "model_policy_id",
    "data_retention_profile",
}
_FORBIDDEN_NAME_FRAGMENTS = (
    "secret",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "password",
    "token",
)


def empty_project_settings() -> dict[str, Any]:
    return {
        "default_locale": "en",
        "timezone": "UTC",
        "cost_budget_default": None,
        "quality_profile": "balanced",
        "model_policy_id": None,
        "data_retention_profile": "standard",
    }


def normalize_project_settings(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = empty_project_settings()
    if value is not None:
        unknown = set(value) - _ALLOWED_KEYS
        if unknown:
            raise ProjectSettingsError(f"unknown project setting(s): {sorted(unknown)}")
        for key in value:
            lowered = key.lower()
            if any(fragment in lowered for fragment in _FORBIDDEN_NAME_FRAGMENTS):
                raise ProjectSettingsError("provider secrets do not belong in project settings")
        raw.update(value)

    locale = raw["default_locale"]
    timezone = raw["timezone"]
    quality_profile = raw["quality_profile"]
    retention = raw["data_retention_profile"]
    model_policy_id = raw["model_policy_id"]

    if not isinstance(locale, str) or not 1 <= len(locale.strip()) <= 64:
        raise ProjectSettingsError("default_locale is invalid")
    if not isinstance(timezone, str) or not 1 <= len(timezone.strip()) <= 100:
        raise ProjectSettingsError("timezone is invalid")
    if quality_profile not in {"fast", "balanced", "high_quality"}:
        raise ProjectSettingsError("quality_profile is invalid")
    if not isinstance(retention, str) or not 1 <= len(retention.strip()) <= 100:
        raise ProjectSettingsError("data_retention_profile is invalid")
    if model_policy_id is not None and (
        not isinstance(model_policy_id, str) or not 1 <= len(model_policy_id.strip()) <= 160
    ):
        raise ProjectSettingsError("model_policy_id is invalid")

    budget = raw["cost_budget_default"]
    normalized_budget: str | None
    if budget is None:
        normalized_budget = None
    else:
        if isinstance(budget, bool):
            raise ProjectSettingsError("cost_budget_default is invalid")
        try:
            amount = Decimal(str(budget))
        except (InvalidOperation, ValueError) as exc:
            raise ProjectSettingsError("cost_budget_default is invalid") from exc
        if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
            raise ProjectSettingsError("cost_budget_default is invalid")
        normalized_budget = format(amount.normalize(), "f")

    return {
        "default_locale": locale.strip(),
        "timezone": timezone.strip(),
        "cost_budget_default": normalized_budget,
        "quality_profile": quality_profile,
        "model_policy_id": model_policy_id.strip() if isinstance(model_policy_id, str) else None,
        "data_retention_profile": retention.strip(),
    }
