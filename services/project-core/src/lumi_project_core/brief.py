from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any


class BriefValidationError(ValueError):
    pass


_DELIVERABLE_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def empty_brief() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "objective": "",
        "audience": [],
        "brand_context": "",
        "deliverables": [],
        "channels": [],
        "visual_direction": [],
        "copy_requirements": [],
        "constraint_ids": [],
        "reference_asset_ids": [],
        "locale": "en",
        "notes": "",
    }


def _bounded_strings(value: Any, label: str, *, maximum: int, item_max: int) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise BriefValidationError(f"{label} must be an array with at most {maximum} items")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > item_max:
            raise BriefValidationError(f"invalid {label} item")
        result.append(item.strip())
    return result


def normalize_brief(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(empty_brief())
    if value is not None:
        unknown = set(value) - set(raw)
        if unknown:
            raise BriefValidationError(f"unknown brief field(s): {sorted(unknown)}")
        raw.update(value)
    if raw["schema_version"] != "1.0":
        raise BriefValidationError("brief schema_version must be 1.0")

    objective = raw["objective"]
    brand_context = raw["brand_context"]
    locale = raw["locale"]
    notes = raw["notes"]
    if not isinstance(objective, str) or len(objective) > 5000:
        raise BriefValidationError("objective is invalid")
    if not isinstance(brand_context, str) or len(brand_context) > 10000:
        raise BriefValidationError("brand_context is invalid")
    if not isinstance(locale, str) or not 1 <= len(locale.strip()) <= 64:
        raise BriefValidationError("locale is invalid")
    if not isinstance(notes, str) or len(notes) > 10000:
        raise BriefValidationError("notes are invalid")

    audience = _bounded_strings(raw["audience"], "audience", maximum=50, item_max=500)
    channels = _bounded_strings(raw["channels"], "channels", maximum=50, item_max=100)
    visual_direction = _bounded_strings(
        raw["visual_direction"], "visual_direction", maximum=100, item_max=1000
    )
    copy_requirements = _bounded_strings(
        raw["copy_requirements"], "copy_requirements", maximum=100, item_max=2000
    )
    constraint_ids = _bounded_strings(
        raw["constraint_ids"], "constraint_ids", maximum=500, item_max=160
    )
    reference_asset_ids = _bounded_strings(
        raw["reference_asset_ids"], "reference_asset_ids", maximum=200, item_max=160
    )
    if len(constraint_ids) != len(set(constraint_ids)):
        raise BriefValidationError("constraint_ids must be unique")
    if len(reference_asset_ids) != len(set(reference_asset_ids)):
        raise BriefValidationError("reference_asset_ids must be unique")

    deliverables = raw["deliverables"]
    if not isinstance(deliverables, list) or len(deliverables) > 100:
        raise BriefValidationError("deliverables must contain at most 100 items")
    normalized_deliverables: list[dict[str, Any]] = []
    keys: set[str] = set()
    allowed = {"key", "kind", "quantity", "width", "height", "unit", "notes"}
    for item in deliverables:
        if not isinstance(item, Mapping) or set(item) - allowed:
            raise BriefValidationError("invalid deliverable object")
        key = item.get("key")
        kind = item.get("kind")
        quantity = item.get("quantity")
        if not isinstance(key, str) or _DELIVERABLE_KEY.fullmatch(key) is None:
            raise BriefValidationError("deliverable key is invalid")
        if key in keys:
            raise BriefValidationError("deliverable keys must be unique")
        keys.add(key)
        if not isinstance(kind, str) or not kind.strip() or len(kind) > 100:
            raise BriefValidationError("deliverable kind is invalid")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 1000:
            raise BriefValidationError("deliverable quantity is invalid")
        row: dict[str, Any] = {"key": key, "kind": kind.strip(), "quantity": quantity}
        for dimension in ("width", "height"):
            dimension_value = item.get(dimension)
            if dimension_value is not None:
                if (
                    not isinstance(dimension_value, int)
                    or isinstance(dimension_value, bool)
                    or not 1 <= dimension_value <= 100000
                ):
                    raise BriefValidationError(f"deliverable {dimension} is invalid")
                row[dimension] = dimension_value
        unit = item.get("unit")
        if unit is not None:
            if unit not in {"px", "mm", "cm", "in", "pt"}:
                raise BriefValidationError("deliverable unit is invalid")
            row["unit"] = unit
        deliverable_notes = item.get("notes")
        if deliverable_notes is not None:
            if not isinstance(deliverable_notes, str) or len(deliverable_notes) > 2000:
                raise BriefValidationError("deliverable notes are invalid")
            row["notes"] = deliverable_notes
        normalized_deliverables.append(row)

    return {
        "schema_version": "1.0",
        "objective": objective.strip(),
        "audience": audience,
        "brand_context": brand_context.strip(),
        "deliverables": normalized_deliverables,
        "channels": channels,
        "visual_direction": visual_direction,
        "copy_requirements": copy_requirements,
        "constraint_ids": constraint_ids,
        "reference_asset_ids": reference_asset_ids,
        "locale": locale.strip(),
        "notes": notes,
    }


def brief_hash(value: Mapping[str, Any]) -> str:
    normalized = normalize_brief(value)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
