from __future__ import annotations

from dataclasses import dataclass

from .model import AssetAnalysisRecord, AssetRegion, OcrBlock


@dataclass(frozen=True)
class IdentityEvidenceBundle:
    organization_id: str
    asset_id: str
    asset_version: str
    index_id: str
    index_version: str
    checksum_sha256: str
    ocr_blocks: tuple[OcrBlock, ...]
    regions: tuple[AssetRegion, ...]
    embedding: tuple[float, ...] | None
    embedding_model_id: str
    embedding_model_version: str
    preprocessor_version: str


def identity_evidence_from_analysis(record: AssetAnalysisRecord) -> IdentityEvidenceBundle:
    """Expose analysis evidence to NODE-44 without performing identity scoring here."""

    embedding_snapshot = record.analyzer_bundle.embedding
    if embedding_snapshot is None:
        raise ValueError("IDENTITY_EVIDENCE_EMBEDDING_UNAVAILABLE")
    return IdentityEvidenceBundle(
        organization_id=record.organization_id,
        asset_id=record.asset_id,
        asset_version=record.asset_version,
        index_id=record.index_id,
        index_version=record.index_version,
        checksum_sha256=record.checksum_sha256,
        ocr_blocks=record.ocr_blocks,
        regions=record.regions,
        embedding=record.embedding,
        embedding_model_id=embedding_snapshot.model_id,
        embedding_model_version=embedding_snapshot.model_version,
        preprocessor_version=embedding_snapshot.preprocessor_version,
    )
