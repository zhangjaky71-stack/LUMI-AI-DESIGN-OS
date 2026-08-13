from __future__ import annotations

from typing import Any


def rights_from_assertion(
    assertion: str,
    *,
    asset_id: str,
    organization_id: str,
    source_reference: str | None = None,
) -> dict[str, Any]:
    normalized = assertion.strip().upper()
    if normalized == "USER_OWNED":
        return {
            "subject_type": "ASSET",
            "subject_id": asset_id,
            "organization_id": organization_id,
            "source_type": "USER_UPLOAD",
            "owner_assertion": "USER_OWNED",
            "license_type": "OWNED",
            "commercial_use": "UNKNOWN",
            "redistribution": "UNKNOWN",
            "training_use": "UNKNOWN",
            "attribution_required": False,
            "source_reference": source_reference,
            "review_status": "ASSERTED",
        }
    if normalized == "LICENSED":
        return {
            "subject_type": "ASSET",
            "subject_id": asset_id,
            "organization_id": organization_id,
            "source_type": "LICENSED",
            "owner_assertion": "LICENSED",
            "license_type": "UNKNOWN",
            "commercial_use": "UNKNOWN",
            "redistribution": "UNKNOWN",
            "training_use": "UNKNOWN",
            "attribution_required": False,
            "source_reference": source_reference,
            "review_status": "ASSERTED",
        }
    if normalized == "UNKNOWN":
        return {
            "subject_type": "ASSET",
            "subject_id": asset_id,
            "organization_id": organization_id,
            "source_type": "UNKNOWN",
            "owner_assertion": None,
            "license_type": "UNKNOWN",
            "commercial_use": "UNKNOWN",
            "redistribution": "UNKNOWN",
            "training_use": "UNKNOWN",
            "attribution_required": False,
            "source_reference": source_reference,
            "review_status": "UNREVIEWED",
        }
    raise ValueError("RIGHTS_ASSERTION_INVALID")
