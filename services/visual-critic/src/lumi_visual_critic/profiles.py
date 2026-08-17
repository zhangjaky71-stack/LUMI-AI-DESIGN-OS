from __future__ import annotations

from .model import QualityDimension as D
from .model import QualityProfileKey, QualityProfileSnapshot


_ALL = {
    D.CONSTRAINT_COMPLIANCE,
    D.COMPOSITION,
    D.VISUAL_HIERARCHY,
    D.ALIGNMENT_SPACING,
    D.TYPOGRAPHY_READABILITY,
    D.CONTRAST,
    D.BRAND_CONSISTENCY,
    D.IDENTITY_CONSISTENCY,
    D.TEXT_ACCURACY,
    D.LOGO_INTEGRITY,
    D.QR_READABILITY,
    D.IMAGE_DEFECTS,
    D.RESOLUTION_EXPORT_READINESS,
}


def _profile(
    *,
    key: QualityProfileKey,
    weights: dict[D, float],
    thresholds: dict[D, float],
    pass_score: float,
    warning_score: float,
    low_confidence: float,
    hard: frozenset[D],
    required: frozenset[D],
) -> QualityProfileSnapshot:
    return QualityProfileSnapshot(
        profile_id=f"quality-profile:{key.value}:v1",
        key=key,
        version=1,
        weights=weights,
        thresholds=thresholds,
        overall_pass_threshold=pass_score,
        warning_threshold=warning_score,
        low_confidence_threshold=low_confidence,
        hard_dimensions=hard,
        required_dimensions=required,
        visual_grader_required=True,
    )


def _weights(**overrides: float) -> dict[D, float]:
    base = {dimension: 1.0 for dimension in _ALL}
    by_value = {dimension.value: dimension for dimension in _ALL}
    for key, value in overrides.items():
        base[by_value[key]] = value
    return base


def _thresholds(default: float, **overrides: float) -> dict[D, float]:
    values = {dimension: default for dimension in _ALL}
    by_value = {dimension.value: dimension for dimension in _ALL}
    for key, value in overrides.items():
        values[by_value[key]] = value
    return values


BUILTIN_PROFILES: dict[QualityProfileKey, QualityProfileSnapshot] = {
    QualityProfileKey.EXPLORATION: _profile(
        key=QualityProfileKey.EXPLORATION,
        weights=_weights(composition=1.4, visual_hierarchy=1.3),
        thresholds=_thresholds(60, constraint_compliance=90, qr_readability=90),
        pass_score=68,
        warning_score=58,
        low_confidence=0.45,
        hard=frozenset({D.CONSTRAINT_COMPLIANCE, D.QR_READABILITY}),
        required=frozenset(_ALL),
    ),
    QualityProfileKey.PRODUCTION_WEB: _profile(
        key=QualityProfileKey.PRODUCTION_WEB,
        weights=_weights(
            constraint_compliance=2.0,
            typography_readability=1.7,
            contrast=1.5,
            resolution_export_readiness=1.8,
        ),
        thresholds=_thresholds(
            72,
            constraint_compliance=95,
            typography_readability=78,
            contrast=76,
            resolution_export_readiness=95,
        ),
        pass_score=78,
        warning_score=70,
        low_confidence=0.60,
        hard=frozenset(
            {
                D.CONSTRAINT_COMPLIANCE,
                D.QR_READABILITY,
                D.RESOLUTION_EXPORT_READINESS,
            }
        ),
        required=frozenset(_ALL),
    ),
    QualityProfileKey.BRAND_STRICT: _profile(
        key=QualityProfileKey.BRAND_STRICT,
        weights=_weights(
            brand_consistency=2.5,
            logo_integrity=2.5,
            typography_readability=1.8,
            constraint_compliance=2.0,
        ),
        thresholds=_thresholds(
            76,
            brand_consistency=92,
            logo_integrity=95,
            constraint_compliance=95,
        ),
        pass_score=84,
        warning_score=76,
        low_confidence=0.70,
        hard=frozenset(
            {
                D.CONSTRAINT_COMPLIANCE,
                D.BRAND_CONSISTENCY,
                D.LOGO_INTEGRITY,
                D.QR_READABILITY,
            }
        ),
        required=frozenset(_ALL),
    ),
    QualityProfileKey.PRODUCT_STRICT: _profile(
        key=QualityProfileKey.PRODUCT_STRICT,
        weights=_weights(
            identity_consistency=3.0,
            image_defects=2.0,
            constraint_compliance=2.0,
            resolution_export_readiness=1.5,
        ),
        thresholds=_thresholds(
            76,
            identity_consistency=94,
            image_defects=88,
            constraint_compliance=95,
        ),
        pass_score=85,
        warning_score=78,
        low_confidence=0.75,
        hard=frozenset(
            {
                D.CONSTRAINT_COMPLIANCE,
                D.IDENTITY_CONSISTENCY,
                D.QR_READABILITY,
            }
        ),
        required=frozenset(_ALL),
    ),
    QualityProfileKey.PRINT: _profile(
        key=QualityProfileKey.PRINT,
        weights=_weights(
            resolution_export_readiness=3.0,
            typography_readability=2.0,
            contrast=1.8,
            constraint_compliance=2.0,
        ),
        thresholds=_thresholds(
            78,
            resolution_export_readiness=97,
            typography_readability=82,
            constraint_compliance=96,
        ),
        pass_score=86,
        warning_score=80,
        low_confidence=0.70,
        hard=frozenset(
            {
                D.CONSTRAINT_COMPLIANCE,
                D.RESOLUTION_EXPORT_READINESS,
                D.QR_READABILITY,
            }
        ),
        required=frozenset(_ALL),
    ),
    QualityProfileKey.SOCIAL_FAST: _profile(
        key=QualityProfileKey.SOCIAL_FAST,
        weights=_weights(
            visual_hierarchy=1.8,
            composition=1.6,
            text_accuracy=1.5,
        ),
        thresholds=_thresholds(68, constraint_compliance=92, qr_readability=92),
        pass_score=74,
        warning_score=66,
        low_confidence=0.55,
        hard=frozenset({D.CONSTRAINT_COMPLIANCE, D.QR_READABILITY}),
        required=frozenset(_ALL),
    ),
}


def get_builtin_profile(key: QualityProfileKey) -> QualityProfileSnapshot:
    return BUILTIN_PROFILES[key]
