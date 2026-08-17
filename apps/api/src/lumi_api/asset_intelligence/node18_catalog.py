from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_asset_intelligence import VerifiedReadyAsset


class Node18AssetCatalogAdapter:
    """Tenant-scoped READY Asset view reusing NODE-18 rights and storage facts."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _record(row: Mapping[str, Any]) -> VerifiedReadyAsset:
        semantic = row["semantic_metadata_json"] or {}
        rights = row["rights_level"] or "unknown"
        training_authorized = bool(semantic.get("training_authorized", False))
        tags = tuple(str(v) for v in semantic.get("permission_tags", []))
        brand_id_raw = semantic.get("brand_id")
        brand_id = UUID(str(brand_id_raw)) if brand_id_raw else None
        technical = row["file_metadata"] or {}
        for key in ("width", "height", "duration_ms", "color_profile", "has_alpha"):
            if row.get(key) is not None:
                technical[key] = row[key]
        user_metadata = semantic.get("user_metadata", {})
        preview_ref = None
        if row.get("preview_bucket") and row.get("preview_key"):
            preview_ref = f"asset-preview://{row['preview_bucket']}/{row['preview_key']}"
        return VerifiedReadyAsset(
            asset_id=row["id"],
            organization_id=row["organization_id"],
            project_id=row["project_id"],
            brand_id=brand_id,
            status=str(row["status"]),
            source=str(row["source"]),
            mime_type=str(row["mime_type"] or row["declared_mime_type"]),
            media_kind=str(row["media_kind"]),
            checksum_sha256=str(row["checksum_sha256"]),
            byte_size=int(row["byte_size"]),
            rights_level=str(rights),
            commercial_use=bool(row["commercial_use"]),
            training_authorized=training_authorized,
            permission_tags=tags,
            preview_ref=preview_ref,
            technical_metadata=technical,
            user_metadata=user_metadata,
            created_at=row["created_at"],
            deleted_at=row["deleted_at"],
        )

    def _rows(self, organization_id: UUID, asset_id: UUID | None = None):
        condition = "AND a.id = :asset_id" if asset_id else ""
        return self.session.execute(
            text(f"""
                SELECT a.id, a.organization_id, a.project_id, a.source,
                       a.declared_mime_type, a.mime_type, a.media_kind, a.status,
                       a.semantic_metadata_json, a.created_at, a.deleted_at,
                       f.checksum_sha256, f.byte_size, f.width, f.height,
                       f.duration_ms, f.color_profile, f.has_alpha,
                       f.metadata AS file_metadata,
                       r.rights_level, r.assertion AS rights_assertion,
                       COALESCE(r.commercial_use, false) AS commercial_use,
                       p.bucket AS preview_bucket, p.object_key AS preview_key
                FROM assets a
                JOIN LATERAL (
                    SELECT * FROM asset_files
                    WHERE asset_id = a.id AND organization_id = a.organization_id
                    ORDER BY CASE role WHEN 'original' THEN 0 ELSE 1 END, created_at ASC
                    LIMIT 1
                ) f ON TRUE
                LEFT JOIN asset_rights r
                  ON r.asset_id = a.id AND r.organization_id = a.organization_id
                LEFT JOIN LATERAL (
                    SELECT * FROM asset_previews
                    WHERE asset_id = a.id AND organization_id = a.organization_id
                    ORDER BY created_at DESC LIMIT 1
                ) p ON TRUE
                WHERE a.organization_id = :organization_id
                  AND a.status = 'ready'
                  AND a.deleted_at IS NULL
                  {condition}
                ORDER BY a.created_at, a.id
            """),
            {"organization_id": organization_id, "asset_id": asset_id},
        ).mappings().all()

    def get_asset(self, organization_id: UUID, asset_id: UUID) -> VerifiedReadyAsset | None:
        rows = self._rows(organization_id, asset_id)
        return self._record(rows[0]) if rows else None

    def list_ready_assets(self, organization_id: UUID) -> tuple[VerifiedReadyAsset, ...]:
        return tuple(self._record(row) for row in self._rows(organization_id))
