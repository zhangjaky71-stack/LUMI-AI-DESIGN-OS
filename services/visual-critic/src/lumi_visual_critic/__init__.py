SERVICE_NAME = "visual-critic"
VERSION = "1.0.0"

from .engine import QualityOperationConflict, VisualCriticEngine
from .model import (
    ArtifactQualityInput,
    DimensionAssessment,
    EvidenceKind,
    GraderCalibrationSnapshot,
    QualityDimension,
    QualityEvidence,
    QualityGateStatus,
    QualityProfileKey,
    QualityProfileSnapshot,
    QualityResult,
    QualitySeverity,
    QualitySignalBundle,
    QualityTaskSpec,
    QualityViolation,
    RepairAction,
    RepairActionType,
    VisualGraderResult,
)
from .profiles import BUILTIN_PROFILES, get_builtin_profile
from .repository import InMemoryQualityResultRepository

__all__ = [
    "ArtifactQualityInput",
    "BUILTIN_PROFILES",
    "DimensionAssessment",
    "EvidenceKind",
    "GraderCalibrationSnapshot",
    "InMemoryQualityResultRepository",
    "QualityDimension",
    "QualityEvidence",
    "QualityGateStatus",
    "QualityOperationConflict",
    "QualityProfileKey",
    "QualityProfileSnapshot",
    "QualityResult",
    "QualitySeverity",
    "QualitySignalBundle",
    "QualityTaskSpec",
    "QualityViolation",
    "RepairAction",
    "RepairActionType",
    "VisualCriticEngine",
    "VisualGraderResult",
    "get_builtin_profile",
]
