from __future__ import annotations

from uuid import UUID

from lumi_api.identity_engine.contracts import RegionEvidence
from lumi_api.identity_engine.node45_adapter import AssetIdentityAnalysis

from lumi_asset_intelligence import AssetIndexRepository


class IdentityAnalysisSourceAdapter:
    """Expose active NODE-45 analysis to the NODE-44 identity signal provider."""

    def __init__(self, repository: AssetIndexRepository) -> None:
        self.repository = repository

    def get_identity_analysis(
        self,
        organization_id: UUID,
        asset_id: UUID,
    ) -> AssetIdentityAnalysis | None:
        try:
            index = self.repository.active_index(organization_id)
        except LookupError:
            return None
        value = self.repository.get_analysis(organization_id, asset_id, index.id)
        if value is None or value.state != "READY":
            return None
        region = None
        if value.regions:
            best = max(value.regions, key=lambda item: item.confidence)
            if best.bbox.coordinate_space == "NORMALIZED":
                region = RegionEvidence(
                    source=f"node45:{best.analyzer_id}",
                    x=best.bbox.x,
                    y=best.bbox.y,
                    width=best.bbox.width,
                    height=best.bbox.height,
                    detection_confidence=best.confidence,
                    quality=best.confidence,
                    evidence_refs=value.evidence_refs,
                )
        ocr_text = " ".join(span.text for span in value.ocr_spans) or None
        return AssetIdentityAnalysis(
            asset_id=value.asset_id,
            analyzer_version=value.analyzer_version,
            content_hash=value.checksum_sha256,
            perceptual_hash=value.perceptual_hash,
            embedding=value.embedding or (),
            local_signature=value.local_signature,
            color_signature=value.color_signature,
            brand_region_signature=value.brand_region_signature,
            ocr_text=ocr_text,
            region=region,
            evidence_refs=value.evidence_refs,
        )
