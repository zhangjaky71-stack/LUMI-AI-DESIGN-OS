from __future__ import annotations

from .model import QualityResult, QualityTaskSpec
from .engine import QualityOperationConflict


class InMemoryQualityResultRepository:
    def __init__(self) -> None:
        self._results: dict[str, QualityResult] = {}
        self._operations: dict[tuple[str, str], str] = {}

    def create(
        self,
        *,
        spec: QualityTaskSpec,
        result: QualityResult,
    ) -> QualityResult:
        key = (spec.organization_id, spec.operation_id)
        existing_id = self._operations.get(key)
        if existing_id is not None:
            existing = self._results[existing_id]
            if (
                existing.artifact_version_id != result.artifact_version_id
                or existing.profile_hash != result.profile_hash
            ):
                raise QualityOperationConflict(
                    "QUALITY_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
                )
            return existing
        self._results[result.quality_result_id] = result
        self._operations[key] = result.quality_result_id
        return result

    def get_by_operation(
        self,
        *,
        organization_id: str,
        operation_id: str,
    ) -> QualityResult | None:
        result_id = self._operations.get((organization_id, operation_id))
        return None if result_id is None else self._results[result_id]
