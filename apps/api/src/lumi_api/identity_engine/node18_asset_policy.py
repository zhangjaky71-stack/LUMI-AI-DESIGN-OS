from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IdentityAssetRecord:
    asset_id: UUID
    organization_id: UUID
    status: str
    media_kind: str | None
    rights_assertion: str = "UNKNOWN"
    accessible: bool = True


class Node18AssetSource(Protocol):
    def get_identity_asset(
        self,
        organization_id: UUID,
        asset_id: UUID,
    ) -> IdentityAssetRecord | None: ...


class Node18IdentityAssetPolicy:
    """Reference-asset readiness/tenant gate backed by NODE-18 asset metadata."""

    def __init__(self, source: Node18AssetSource) -> None:
        self.source = source

    def assert_reference_assets_allowed(
        self,
        organization_id: UUID,
        asset_ids: tuple[UUID, ...],
        *,
        identity_type: str,
    ) -> None:
        if not asset_ids:
            raise ValueError("IDENTITY_REFERENCE_ASSET_REQUIRED")
        for asset_id in asset_ids:
            record = self.source.get_identity_asset(organization_id, asset_id)
            if record is None or not record.accessible:
                raise PermissionError("IDENTITY_REFERENCE_ASSET_NOT_ACCESSIBLE")
            if record.organization_id != organization_id:
                raise PermissionError("IDENTITY_REFERENCE_ASSET_TENANT_MISMATCH")
            if record.status.casefold() != "ready":
                raise ValueError("IDENTITY_REFERENCE_ASSET_NOT_READY")
            if record.media_kind not in {"image", "vector"}:
                raise ValueError("IDENTITY_REFERENCE_ASSET_MEDIA_UNSUPPORTED")
            if identity_type == "FACE" and record.rights_assertion == "UNKNOWN":
                raise PermissionError("IDENTITY_FACE_REFERENCE_RIGHTS_UNKNOWN")
