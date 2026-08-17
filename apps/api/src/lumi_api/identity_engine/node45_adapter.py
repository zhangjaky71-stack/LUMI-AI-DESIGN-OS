from __future__ import annotations

import math
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol
from uuid import UUID

from .contracts import (
    CandidateIdentity,
    IdentityReferenceSet,
    IdentityType,
    RegionEvidence,
    SignalBundle,
    SignalName,
    SignalScore,
)


@dataclass(frozen=True, slots=True)
class AssetIdentityAnalysis:
    asset_id: UUID
    analyzer_version: str
    content_hash: str | None = None
    perceptual_hash: str | None = None
    embedding: tuple[float, ...] = ()
    local_signature: tuple[float, ...] = ()
    color_signature: tuple[float, ...] = ()
    brand_region_signature: tuple[float, ...] = ()
    ocr_text: str | None = None
    region: RegionEvidence | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        vectors = (
            self.embedding,
            self.local_signature,
            self.color_signature,
            self.brand_region_signature,
        )
        for vector in vectors:
            if any(not math.isfinite(value) for value in vector):
                raise ValueError("IDENTITY_ANALYSIS_VECTOR_NON_FINITE")


class AssetIntelligenceSource(Protocol):
    def get_identity_analysis(
        self,
        organization_id: UUID,
        asset_id: UUID,
    ) -> AssetIdentityAnalysis | None: ...


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float | None:
    if not left or not right or len(left) != len(right):
        return None
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return None
    cosine = max(-1.0, min(1.0, dot / (left_norm * right_norm)))
    return max(0.0, cosine) * 100.0


def _perceptual(left: str | None, right: str | None) -> float | None:
    if not left or not right or len(left) != len(right):
        return None
    try:
        left_bits = bin(int(left, 16))[2:].zfill(len(left) * 4)
        right_bits = bin(int(right, 16))[2:].zfill(len(right) * 4)
    except ValueError:
        return None
    distance = sum(a != b for a, b in zip(left_bits, right_bits, strict=True))
    return (1.0 - distance / len(left_bits)) * 100.0


def _text_similarity(left: str | None, right: str | None) -> float | None:
    if not left or not right:
        return None
    a = " ".join(left.casefold().split())
    b = " ".join(right.casefold().split())
    if not a or not b:
        return None
    return SequenceMatcher(a=a, b=b, autojunk=False).ratio() * 100.0


def _score(
    name: SignalName,
    value: float | None,
    *,
    evidence_refs: tuple[str, ...],
) -> SignalScore:
    if value is None:
        return SignalScore(
            name=name,
            score=0.0,
            confidence=0.0,
            available=False,
            evidence_refs=evidence_refs,
        )
    return SignalScore(
        name=name,
        score=max(0.0, min(100.0, value)),
        confidence=1.0,
        available=True,
        evidence_refs=evidence_refs,
    )


class Node45AssetIntelligenceSignalProvider:
    """Adapter from NODE-45-style asset analyses to NODE-44 identity signals."""

    def __init__(self, source: AssetIntelligenceSource) -> None:
        self.source = source

    def evaluate(
        self,
        reference_set: IdentityReferenceSet,
        candidate: CandidateIdentity,
    ) -> SignalBundle:
        if reference_set.identity_type is IdentityType.FACE:
            raise ValueError("IDENTITY_FACE_NODE45_PERSISTENT_ANALYSIS_FORBIDDEN")
        if candidate.asset_id is None:
            raise ValueError("IDENTITY_NODE45_CANDIDATE_ASSET_REQUIRED")
        candidate_analysis = self.source.get_identity_analysis(
            reference_set.organization_id,
            candidate.asset_id,
        )
        if candidate_analysis is None:
            raise ValueError("IDENTITY_NODE45_CANDIDATE_ANALYSIS_MISSING")
        references = tuple(
            analysis
            for asset_id in reference_set.canonical_asset_ids
            if (
                analysis := self.source.get_identity_analysis(
                    reference_set.organization_id,
                    asset_id,
                )
            )
            is not None
        )
        if not references:
            raise ValueError("IDENTITY_NODE45_REFERENCE_ANALYSIS_MISSING")
        per_reference = tuple(
            self._signals(reference_set.identity_type, ref, candidate_analysis)
            for ref in references
        )
        signal_names = sorted(
            {signal.name for group in per_reference for signal in group},
            key=lambda item: item.value,
        )
        combined = []
        for name in signal_names:
            values = tuple(
                signal
                for group in per_reference
                for signal in group
                if signal.name is name
            )
            available = tuple(signal for signal in values if signal.available)
            if not available:
                combined.append(values[0])
                continue
            combined.append(max(available, key=lambda signal: signal.score))
        versions = sorted(
            {candidate_analysis.analyzer_version, *(ref.analyzer_version for ref in references)}
        )
        evidence = tuple(
            sorted(
                {
                    *candidate_analysis.evidence_refs,
                    *(item for ref in references for item in ref.evidence_refs),
                }
            )
        )
        return SignalBundle(
            region=candidate.declared_region or candidate_analysis.region,
            signals=tuple(combined),
            provider_version="node45:" + "+".join(versions),
            evidence_refs=evidence,
        )

    def _signals(
        self,
        identity_type: IdentityType,
        reference: AssetIdentityAnalysis,
        candidate: AssetIdentityAnalysis,
    ) -> tuple[SignalScore, ...]:
        refs = tuple(sorted({*reference.evidence_refs, *candidate.evidence_refs}))
        if identity_type is IdentityType.LOGO:
            exact = None
            if (
                reference.content_hash
                and candidate.content_hash
                and reference.content_hash == candidate.content_hash
            ):
                exact = 100.0
            return (
                _score(SignalName.EXACT_HASH, exact, evidence_refs=refs),
                _score(
                    SignalName.PERCEPTUAL,
                    _perceptual(reference.perceptual_hash, candidate.perceptual_hash),
                    evidence_refs=refs,
                ),
                _score(
                    SignalName.FEATURE_MATCH,
                    _cosine(reference.local_signature, candidate.local_signature),
                    evidence_refs=refs,
                ),
                _score(
                    SignalName.OCR_WORDMARK,
                    _text_similarity(reference.ocr_text, candidate.ocr_text),
                    evidence_refs=refs,
                ),
            )
        shape = _cosine(reference.local_signature, candidate.local_signature)
        color = _cosine(reference.color_signature, candidate.color_signature)
        shape_color_values = tuple(value for value in (shape, color) if value is not None)
        shape_color = (
            sum(shape_color_values) / len(shape_color_values)
            if shape_color_values
            else None
        )
        return (
            _score(
                SignalName.MULTIMODAL_EMBEDDING,
                _cosine(reference.embedding, candidate.embedding),
                evidence_refs=refs,
            ),
            _score(
                SignalName.LOCAL_FEATURE,
                _cosine(reference.local_signature, candidate.local_signature),
                evidence_refs=refs,
            ),
            _score(SignalName.SHAPE_COLOR, shape_color, evidence_refs=refs),
            _score(
                SignalName.BRAND_REGION,
                _cosine(
                    reference.brand_region_signature,
                    candidate.brand_region_signature,
                ),
                evidence_refs=refs,
            ),
            _score(SignalName.VLM_STRUCTURED, None, evidence_refs=refs),
        )
