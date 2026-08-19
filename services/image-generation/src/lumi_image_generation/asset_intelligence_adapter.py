from __future__ import annotations

from typing import cast

from lumi_asset_intelligence.model import (
    AccessScope,
    AssetIndexRepository,
    AssetSearchFilters,
    Rights as AssetRights,
)

from .model import AuthorizedReference, ImageGenerationSpec, ImageReference


class ReferenceAuthorizationError(ValueError):
    pass


class AssetIntelligenceReferenceAuthorizer:
    """Scope-first reference authorization using NODE-45's repository boundary."""

    def __init__(
        self,
        repository: AssetIndexRepository,
        *,
        active_index_id: str,
        permission_tags: tuple[str, ...] = (),
        require_commercial_rights: bool = False,
    ) -> None:
        self.repository = repository
        self.active_index_id = active_index_id
        self.permission_tags = permission_tags
        self.require_commercial_rights = require_commercial_rights

    def authorize(
        self,
        spec: ImageGenerationSpec,
        references: tuple[ImageReference, ...],
    ) -> tuple[AuthorizedReference, ...]:
        if not references:
            return ()
        allowed_rights = cast(
            tuple[AssetRights, ...],
            (
                ("USER_OWNED", "LICENSED")
                if self.require_commercial_rights
                else ("USER_OWNED", "LICENSED", "UNKNOWN")
            ),
        )
        scope = AccessScope(
            organization_id=spec.organization_id,
            permission_tags=self.permission_tags,
            allowed_rights=allowed_rights,
            commercial_use=self.require_commercial_rights,
        )
        candidates = self.repository.scoped_candidates(
            scope,
            AssetSearchFilters(),
            self.active_index_id,
        )
        by_key = {(item.asset_id, item.asset_version): item for item in candidates}

        authorized: list[AuthorizedReference] = []
        for reference in references:
            record = by_key.get((reference.asset_id, reference.asset_version))
            if record is None:
                raise ReferenceAuthorizationError(
                    f"GENERATION_REFERENCE_NOT_ACCESSIBLE:{reference.asset_id}@{reference.asset_version}"
                )
            signals = self.repository.usage_signals(spec.organization_id, reference.asset_id)
            approval_state = None
            if signals:
                approval_state = max(signals, key=lambda item: item.occurred_at).signal
            authorized.append(
                AuthorizedReference(
                    asset_id=record.asset_id,
                    asset_version=record.asset_version,
                    role=reference.role,
                    source=reference.source,
                    durable_ref=f"asset:{record.asset_id}@{record.asset_version}",
                    rights=record.rights,
                    commercial_use_allowed=record.commercial_use_allowed,
                    checksum_sha256=record.checksum_sha256,
                    mime_type=record.mime_type,
                    approval_state=approval_state,
                )
            )
        return tuple(authorized)
