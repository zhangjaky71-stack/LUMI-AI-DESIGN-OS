from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from .model import ArtifactFile, ArtifactVersion, ProvenanceRecord, RightsRecord


def build_export_manifest(
    version: ArtifactVersion,
    provenance: ProvenanceRecord,
    files: Iterable[ArtifactFile],
    rights: Iterable[RightsRecord],
    *,
    created_at: datetime,
) -> dict[str, Any]:
    if provenance.artifact_version_id != version.id:
        raise ValueError("provenance/version mismatch")
    if provenance.organization_id != version.organization_id:
        raise ValueError("provenance tenant mismatch")

    file_rows = tuple(file for file in files if file.artifact_version_id == version.id)
    rights_rows = tuple(right for right in rights if right.organization_id == version.organization_id)
    sources = sorted(
        set(provenance.input_asset_ids).union(provenance.input_artifact_version_ids)
    )
    models = []
    if provenance.provider or provenance.model:
        models.append("/".join(part for part in (provenance.provider, provenance.model) if part))

    return {
        "schema_version": "1.0",
        "artifact_version": version.id,
        "created_at": created_at.isoformat(),
        "sources": sources,
        "models": models,
        "rights": [
            {
                "subject_type": right.subject_type,
                "subject_id": right.subject_id,
                "source_type": right.source_type,
                "license_type": right.license_type,
                "commercial_use": right.commercial_use,
                "redistribution": right.redistribution,
                "attribution_required": right.attribution_required,
                "review_status": right.review_status,
            }
            for right in sorted(rights_rows, key=lambda item: (item.subject_type, item.subject_id))
        ],
        "checksums": [
            {"file_id": file.id, "sha256": file.checksum_sha256}
            for file in sorted(file_rows, key=lambda item: item.id)
        ],
        "constraint_snapshot_hash": version.constraint_snapshot_hash,
        "code_git_sha": provenance.code_git_sha,
    }
