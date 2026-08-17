from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from .contracts import IdentityReferenceSet


class IdentityNotFound(LookupError):
    code = "IDENTITY_REFERENCE_SET_NOT_FOUND"


class InMemoryIdentityRepository:
    def __init__(self) -> None:
        self._versions: dict[tuple[UUID, UUID], list[IdentityReferenceSet]] = defaultdict(list)
        self.validations: list[object] = []
        self.calibrations: list[object] = []

    def reserve_version(self, organization_id: UUID, identity_id: UUID) -> int:
        return len(self._versions[(organization_id, identity_id)]) + 1

    def save_reference_set(self, value: IdentityReferenceSet) -> None:
        key = (value.organization_id, value.id)
        expected = len(self._versions[key]) + 1
        if value.version != expected:
            raise ValueError("IDENTITY_VERSION_CONFLICT")
        self._versions[key].append(value)

    def get_latest(self, organization_id: UUID, identity_id: UUID) -> IdentityReferenceSet:
        values = self._versions.get((organization_id, identity_id))
        if not values:
            raise IdentityNotFound(str(identity_id))
        return values[-1]

    def save_validation(self, value: object) -> None:
        self.validations.append(value)

    def save_calibration(self, value: object) -> None:
        self.calibrations.append(value)
