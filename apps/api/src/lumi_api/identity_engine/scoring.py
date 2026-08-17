from __future__ import annotations

from .contracts import IdentityType, SignalName, SignalScore

WEIGHTS: dict[IdentityType, dict[SignalName, float]] = {
    IdentityType.LOGO: {
        SignalName.EXACT_HASH: 0.35,
        SignalName.PERCEPTUAL: 0.25,
        SignalName.FEATURE_MATCH: 0.25,
        SignalName.OCR_WORDMARK: 0.15,
    },
    IdentityType.PRODUCT: {
        SignalName.MULTIMODAL_EMBEDDING: 0.30,
        SignalName.LOCAL_FEATURE: 0.25,
        SignalName.SHAPE_COLOR: 0.20,
        SignalName.BRAND_REGION: 0.15,
        SignalName.VLM_STRUCTURED: 0.10,
    },
    IdentityType.CHARACTER: {
        SignalName.MULTIMODAL_EMBEDDING: 0.35,
        SignalName.LOCAL_FEATURE: 0.30,
        SignalName.SHAPE_COLOR: 0.20,
        SignalName.VLM_STRUCTURED: 0.15,
    },
    IdentityType.FACE: {
        SignalName.LOCAL_FEATURE: 0.60,
        SignalName.VLM_STRUCTURED: 0.40,
    },
    IdentityType.STYLE_REFERENCE: {
        SignalName.MULTIMODAL_EMBEDDING: 0.55,
        SignalName.SHAPE_COLOR: 0.20,
        SignalName.VLM_STRUCTURED: 0.25,
    },
}


def combine_signals(
    identity_type: IdentityType,
    signals: tuple[SignalScore, ...],
    *,
    region_quality: float,
    region_confidence: float,
) -> tuple[float | None, float, int, float]:
    weights = WEIGHTS[identity_type]
    available = [s for s in signals if s.available and s.name in weights]
    if not available:
        return None, 0.0, 0, 0.0
    denominator = sum(weights[s.name] * max(s.confidence, 0.05) for s in available)
    if denominator <= 0:
        return None, 0.0, 0, 0.0
    score = sum(
        weights[s.name] * max(s.confidence, 0.05) * s.score
        for s in available
    ) / denominator
    coverage = sum(weights[s.name] for s in available) / sum(weights.values())
    mean_signal_conf = sum(
        weights[s.name] * s.confidence for s in available
    ) / sum(weights[s.name] for s in available)
    confidence = min(
        1.0,
        coverage * mean_signal_conf * region_quality * region_confidence,
    )
    return round(score, 6), round(confidence, 6), len(available), round(coverage, 6)
