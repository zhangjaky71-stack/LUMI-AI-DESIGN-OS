from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from lumi_project_core import (
    BriefValidationError,
    CursorError,
    ProjectCursor,
    ProjectListFilter,
    ProjectSettingsError,
    brief_hash,
    can_start_paid_command,
    decode_cursor,
    encode_cursor,
    normalize_brief,
    normalize_project_settings,
    restore,
)


def _brief() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "objective": "为东京咖啡品牌建立夏季视觉活动",
        "audience": ["通勤白领", "设计敏感用户"],
        "brand_context": "极简、低饱和、保留现有 Logo。",
        "deliverables": [
            {"key": "poster-main", "kind": "poster", "quantity": 1, "width": 750, "height": 1624, "unit": "px"}
        ],
        "channels": ["app", "social"],
        "visual_direction": ["minimal", "premium", "soft light"],
        "copy_requirements": ["无衬线", "中文主文案保持简洁"],
        "constraint_ids": ["constraint:keep-logo", "constraint:keep-qr"],
        "reference_asset_ids": ["asset:logo", "asset:product"],
        "locale": "zh-CN",
        "notes": "二维码位置和大小保持不变。",
    }


def test_brief_normalization_and_hash_are_unicode_deterministic() -> None:
    brief = _brief()
    normalized = normalize_brief(brief)
    assert normalized["objective"] == brief["objective"]
    assert brief_hash(brief) == brief_hash(dict(reversed(list(brief.items()))))
    assert len(brief_hash(brief)) == 64


def test_brief_rejects_duplicate_refs_unknown_fields_and_bad_deliverable_key() -> None:
    duplicate = _brief()
    duplicate["constraint_ids"] = ["constraint:x", "constraint:x"]
    with pytest.raises(BriefValidationError):
        normalize_brief(duplicate)

    unknown = _brief()
    unknown["provider_secret"] = "nope"
    with pytest.raises(BriefValidationError):
        normalize_brief(unknown)

    invalid_key = _brief()
    invalid_key["deliverables"] = [{"key": "Poster Main", "kind": "poster", "quantity": 1}]
    with pytest.raises(BriefValidationError):
        normalize_brief(invalid_key)


def test_project_settings_are_strict_and_never_accept_provider_secrets() -> None:
    normalized = normalize_project_settings(
        {
            "default_locale": "zh-CN",
            "timezone": "Asia/Tokyo",
            "cost_budget_default": "125.50",
            "quality_profile": "high_quality",
            "model_policy_id": "policy:brand-high-quality",
            "data_retention_profile": "standard",
        }
    )
    assert normalized["cost_budget_default"] == "125.5"
    with pytest.raises(ProjectSettingsError):
        normalize_project_settings({"openai_api_key": "secret"})
    with pytest.raises(ProjectSettingsError):
        normalize_project_settings({"quality_profile": "magic"})


def test_restore_is_safe_and_paid_commands_require_active_project() -> None:
    assert restore("ARCHIVED") == "paused"
    assert can_start_paid_command("active", deleted=False)
    assert not can_start_paid_command("paused", deleted=False)
    assert not can_start_paid_command("archived", deleted=False)
    assert not can_start_paid_command("active", deleted=True)
    with pytest.raises(ValueError, match="PROJECT_NOT_ARCHIVED"):
        restore("active")


def test_project_cursor_roundtrip_and_invalid_payload() -> None:
    cursor = ProjectCursor(
        created_at=datetime(2026, 8, 13, 4, 0, tzinfo=UTC),
        project_id="01900000-0000-7000-8000-000000000006",
    )
    assert decode_cursor(encode_cursor(cursor)) == cursor
    with pytest.raises(CursorError):
        decode_cursor("not-json")


def test_project_list_filter_rejects_invalid_time_range_and_name_query() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        ProjectListFilter(updated_after=now, updated_before=now - timedelta(seconds=1))
    with pytest.raises(ValueError):
        ProjectListFilter(name_query="   ")
    with pytest.raises(ValueError):
        ProjectListFilter(status="deleted")  # type: ignore[arg-type]
