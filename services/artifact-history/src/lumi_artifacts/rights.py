from __future__ import annotations

from collections.abc import Iterable

from .model import RightsRecord, TriState


def _conservative(values: Iterable[TriState]) -> TriState:
    items = tuple(values)
    if not items:
        return "UNKNOWN"
    if "DENIED" in items:
        return "DENIED"
    if "UNKNOWN" in items:
        return "UNKNOWN"
    return "ALLOWED"


def inherit_rights(
    inputs: Iterable[RightsRecord],
    *,
    artifact_version_id: str,
    organization_id: str,
) -> RightsRecord:
    """Conservatively derive output rights without manufacturing a license guarantee."""
    records = tuple(inputs)
    for record in records:
        if record.organization_id != organization_id:
            raise ValueError("rights inheritance cannot cross tenants")

    license_types = {record.license_type for record in records}
    if len(license_types) == 1:
        license_type = next(iter(license_types))
    else:
        license_type = "UNKNOWN"

    if any(record.review_status == "RESTRICTED" for record in records):
        review_status = "RESTRICTED"
    elif records and all(record.review_status == "VERIFIED" for record in records):
        review_status = "VERIFIED"
    elif records and all(record.review_status in {"ASSERTED", "VERIFIED"} for record in records):
        review_status = "ASSERTED"
    else:
        review_status = "UNREVIEWED"

    return RightsRecord(
        subject_type="ARTIFACT_VERSION",
        subject_id=artifact_version_id,
        organization_id=organization_id,
        source_type="GENERATED",
        owner_assertion=None,
        license_type=license_type,  # type: ignore[arg-type]
        commercial_use=_conservative(record.commercial_use for record in records),
        redistribution=_conservative(record.redistribution for record in records),
        training_use=_conservative(record.training_use for record in records),
        attribution_required=any(record.attribution_required for record in records),
        source_reference=None,
        review_status=review_status,  # type: ignore[arg-type]
    )
