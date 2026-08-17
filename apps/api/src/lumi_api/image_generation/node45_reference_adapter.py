from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_asset_intelligence import VerifiedReadyAsset
from lumi_image_generation import (
    AuthorizedReference,
    ImageGenerationSpec,
    ImageReference,
)
from lumi_api.asset_intelligence.node18_catalog import Node18AssetCatalogAdapter


@dataclass(frozen=True, slots=True)
class ReferenceAccessPolicy:
    allowed_project_ids: tuple[UUID, ...]
    permission_tags: tuple[str, ...] = ()
    commercial_use: bool = True


class Node45ReferenceAuthorizationAdapter:
    """Re-check NODE-18 facts at generation time; NODE-45 ranking never grants rights."""

    def __init__(self, session: Session, policy: ReferenceAccessPolicy) -> None:
        self.session = session
        self.policy = policy
        self.catalog = Node18AssetCatalogAdapter(session)

    def _approval_state(self, organization_id: UUID, asset_id: UUID) -> str:
        row = self.session.execute(
            text("""
                SELECT signal FROM asset_intelligence_usage_signals
                WHERE organization_id=:organization_id AND asset_id=:asset_id
                ORDER BY occurred_at DESC, id DESC
                LIMIT 1
            """),
            {"organization_id": organization_id, "asset_id": asset_id},
        ).mappings().first()
        if row is None:
            return "UNREVIEWED"
        return str(row["signal"])

    def _storage(self, organization_id: UUID, asset_id: UUID) -> tuple[str, str]:
        row = self.session.execute(
            text("""
                SELECT bucket, object_key
                FROM asset_files
                WHERE organization_id = :organization_id
                  AND asset_id = :asset_id
                  AND role IN ('original','sanitized')
                ORDER BY CASE role WHEN 'original' THEN 0 ELSE 1 END, created_at ASC
                LIMIT 1
            """),
            {"organization_id": organization_id, "asset_id": asset_id},
        ).mappings().first()
        if row is None:
            raise PermissionError("GENERATION_REFERENCE_FILE_NOT_AVAILABLE")
        bucket = str(row["bucket"])
        key = str(row["object_key"])
        if "://" in key:
            raise PermissionError("GENERATION_REFERENCE_DURABLE_KEY_REQUIRED")
        return bucket, key

    def _authorize_asset(
        self,
        spec: ImageGenerationSpec,
        reference: ImageReference,
    ) -> AuthorizedReference:
        asset = self.catalog.get_asset(spec.organization_id, reference.asset_id)
        if asset is None:
            raise PermissionError("GENERATION_REFERENCE_NOT_ACCESSIBLE")
        if asset.asset_version != reference.asset_version:
            raise PermissionError("GENERATION_REFERENCE_VERSION_CHANGED")
        if asset.project_id is not None and asset.project_id not in self.policy.allowed_project_ids:
            raise PermissionError("GENERATION_REFERENCE_PROJECT_SCOPE_DENIED")
        required_tags = set(asset.permission_tags)
        if required_tags and not required_tags.issubset(set(self.policy.permission_tags)):
            raise PermissionError("GENERATION_REFERENCE_PERMISSION_DENIED")
        if self.policy.commercial_use:
            if asset.rights_level not in {"owned", "licensed", "public_domain"}:
                raise PermissionError("GENERATION_REFERENCE_RIGHTS_UNKNOWN")
            if not asset.commercial_use:
                raise PermissionError("GENERATION_REFERENCE_COMMERCIAL_USE_DENIED")
        approval_state = self._approval_state(spec.organization_id, reference.asset_id)
        if reference.source.value == "ASSET_RESOLVER" and approval_state != "APPROVED":
            raise PermissionError("GENERATION_RESOLVER_REFERENCE_CONFIRMATION_REQUIRED")
        bucket, key = self._storage(spec.organization_id, reference.asset_id)
        return AuthorizedReference(
            asset_id=asset.asset_id,
            asset_version=asset.asset_version,
            role=reference.role,
            source=reference.source,
            durable_ref=f"{bucket}/{key}",
            rights_level=asset.rights_level,
            commercial_use=asset.commercial_use,
            checksum_sha256=asset.checksum_sha256,
            mime_type=asset.mime_type,
            approval_state=approval_state,
            evidence_refs=(
                f"asset:{asset.asset_id}@{asset.asset_version}",
                f"rights:{asset.rights_level}",
            ),
        )

    def authorize(
        self,
        spec: ImageGenerationSpec,
        references: tuple[ImageReference, ...],
    ) -> tuple[AuthorizedReference, ...]:
        if spec.project_id not in self.policy.allowed_project_ids:
            raise PermissionError("GENERATION_PROJECT_SCOPE_DENIED")
        values = tuple(self._authorize_asset(spec, item) for item in references)
        if len({item.asset_id for item in values}) != len(values):
            raise ValueError("GENERATION_REFERENCE_DUPLICATE_ASSET")
        return values
