from __future__ import annotations

from typing import Protocol

from .model import (
    ArtifactQualityInput,
    GraderCalibrationSnapshot,
    QualityResult,
    QualitySignalBundle,
    QualityTaskSpec,
    VisualGraderResult,
)


class ArtifactQualityInputPort(Protocol):
    def load_exact(
        self,
        *,
        organization_id: str,
        project_id: str,
        artifact_version_id: str,
    ) -> ArtifactQualityInput: ...


class QualitySignalPort(Protocol):
    source_id: str
    deterministic: bool

    async def evaluate(
        self,
        *,
        spec: QualityTaskSpec,
        artifact: ArtifactQualityInput,
    ) -> QualitySignalBundle: ...


class VisualGraderPort(Protocol):
    async def grade(
        self,
        *,
        spec: QualityTaskSpec,
        artifact: ArtifactQualityInput,
        deterministic_signals: tuple[QualitySignalBundle, ...],
    ) -> VisualGraderResult: ...


class GraderCalibrationPort(Protocol):
    def require_current(
        self,
        *,
        expected: GraderCalibrationSnapshot,
    ) -> None: ...


class QualityResultRepositoryPort(Protocol):
    def create(self, *, spec: QualityTaskSpec, result: QualityResult) -> QualityResult: ...

    def get_by_operation(
        self,
        *,
        organization_id: str,
        operation_id: str,
    ) -> QualityResult | None: ...
