from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .contracts import CandidateIdentity, IdentityReferenceSet, SignalBundle


class IdentitySignalProvider(Protocol):
    def evaluate(
        self,
        reference_set: IdentityReferenceSet,
        candidate: CandidateIdentity,
    ) -> SignalBundle: ...


class IdentityRepository(Protocol):
    def reserve_version(self, organization_id: UUID, identity_id: UUID) -> int: ...
    def save_reference_set(self, value: IdentityReferenceSet) -> None: ...
    def get_latest(self, organization_id: UUID, identity_id: UUID) -> IdentityReferenceSet: ...
    def save_validation(self, value: object) -> None: ...
    def save_calibration(self, value: object) -> None: ...


class IdentityAssetPolicy(Protocol):
    def assert_reference_assets_allowed(
        self,
        organization_id: UUID,
        asset_ids: tuple[UUID, ...],
        *,
        identity_type: str,
    ) -> None: ...
