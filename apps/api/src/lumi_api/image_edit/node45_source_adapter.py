from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_image_edit import ImageEditSpec, SourceImageRef
from lumi_api.artifact_engine.service import ArtifactEngineService
from lumi_api.asset_intelligence.node18_catalog import Node18AssetCatalogAdapter


@dataclass(frozen=True, slots=True)
class EditSourceAccessPolicy:
    allowed_project_ids: tuple[UUID, ...]
    permission_tags: tuple[str, ...] = ()
    commercial_use: bool = True


class ArtifactSourceReader(Protocol):
    def assert_source(self, spec: ImageEditSpec) -> None: ...


class Node42ArtifactSourceReader:
    """Validates the immutable source ArtifactVersion before any paid edit call."""

    def __init__(self, service: ArtifactEngineService) -> None:
        self.service = service

    def assert_source(self, spec: ImageEditSpec) -> None:
        version = self.service.repository.get_version(
            UUID(spec.source.artifact_version_id)
        )
        if str(version.organization_id) != spec.organization_id:
            raise PermissionError("IMAGE_EDIT_ARTIFACT_SOURCE_TENANT_DENIED")
        if str(version.artifact_id) != spec.source.artifact_id:
            raise PermissionError("IMAGE_EDIT_ARTIFACT_SOURCE_MISMATCH")
        if version.content_hash != spec.source.checksum_sha256:
            raise PermissionError("IMAGE_EDIT_ARTIFACT_SOURCE_HASH_CHANGED")


class Node45EditSourceAuthorizationAdapter:
    def __init__(
        self,
        session: Session,
        policy: EditSourceAccessPolicy,
        artifact_source: ArtifactSourceReader,
    ) -> None:
        self.session = session
        self.policy = policy
        self.artifact_source = artifact_source
        self.catalog = Node18AssetCatalogAdapter(session)

    def _storage(self, org: UUID, asset: UUID) -> tuple[str, str]:
        row = self.session.execute(
            text("""
                SELECT bucket, object_key
                FROM asset_files
                WHERE organization_id=:organization_id
                  AND asset_id=:asset_id
                  AND role IN ('original','sanitized')
                ORDER BY CASE role WHEN 'original' THEN 0 ELSE 1 END, created_at ASC
                LIMIT 1
            """),
            {"organization_id": org, "asset_id": asset},
        ).mappings().first()
        if row is None:
            raise PermissionError("IMAGE_EDIT_SOURCE_FILE_NOT_AVAILABLE")
        bucket = str(row["bucket"])
        key = str(row["object_key"])
        if "://" in key:
            raise PermissionError("IMAGE_EDIT_SOURCE_DURABLE_KEY_REQUIRED")
        return bucket, key

    def authorize_current(self, spec: ImageEditSpec) -> SourceImageRef:
        self.artifact_source.assert_source(spec)
        organization_id = UUID(spec.organization_id)
        asset_id = UUID(spec.source.asset_id)
        project_id = UUID(spec.project_id)
        if project_id not in self.policy.allowed_project_ids:
            raise PermissionError("IMAGE_EDIT_PROJECT_SCOPE_DENIED")
        asset = self.catalog.get_asset(organization_id, asset_id)
        if asset is None:
            raise PermissionError("IMAGE_EDIT_SOURCE_NOT_ACCESSIBLE")
        if (
            asset.project_id
            and asset.project_id not in self.policy.allowed_project_ids
        ):
            raise PermissionError("IMAGE_EDIT_SOURCE_PROJECT_SCOPE_DENIED")
        if set(asset.permission_tags) - set(self.policy.permission_tags):
            raise PermissionError("IMAGE_EDIT_SOURCE_PERMISSION_DENIED")
        if self.policy.commercial_use and (
            asset.rights_level not in {"owned", "licensed", "public_domain"}
            or not asset.commercial_use
        ):
            raise PermissionError("IMAGE_EDIT_SOURCE_COMMERCIAL_RIGHTS_DENIED")
        width = int(asset.technical_metadata.get("width") or 0)
        height = int(asset.technical_metadata.get("height") or 0)
        if width <= 0 or height <= 0:
            raise PermissionError("IMAGE_EDIT_SOURCE_DIMENSIONS_UNAVAILABLE")
        bucket, key = self._storage(organization_id, asset_id)
        return SourceImageRef(
            spec.organization_id,
            spec.project_id,
            spec.source.artifact_id,
            spec.source.artifact_version_id,
            str(asset.asset_id),
            asset.asset_version,
            f"{bucket}/{key}",
            asset.checksum_sha256,
            width,
            height,
            asset.mime_type,
            asset.rights_level,
            asset.commercial_use,
        )
