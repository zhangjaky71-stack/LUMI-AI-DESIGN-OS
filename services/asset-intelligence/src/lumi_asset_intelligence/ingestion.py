from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .analyzers import validate_bundle_for_index, validate_embedding_dimensions
from .metadata import merge_metadata, system_metadata_from_asset, user_metadata_fields
from .model import (
    AnalyzerOutput,
    AssetAnalysisRecord,
    AssetAnalyzer,
    AssetIndexRepository,
    AssetIndexVersion,
    CapabilityRegistryPort,
    MetadataField,
    VerifiedReadyAsset,
)


@dataclass(frozen=True)
class IngestionResult:
    record: AssetAnalysisRecord | None
    warnings: tuple[str, ...]
    error_code: str | None = None


class AssetIngestionError(ValueError):
    pass


def _analysis_id(asset: VerifiedReadyAsset, index: AssetIndexVersion) -> str:
    payload = {
        "asset_id": asset.asset_id,
        "asset_version": asset.asset_version,
        "checksum_sha256": asset.checksum_sha256,
        "index_id": index.index_id,
        "organization_id": asset.organization_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"asset-analysis:{hashlib.sha256(encoded).hexdigest()}"


def _auto_metadata(output: AnalyzerOutput) -> tuple[MetadataField, ...]:
    fields: list[MetadataField] = []
    for item in output.metadata:
        if item.source != "AUTO":
            raise AssetIngestionError("ANALYZER_METADATA_SOURCE_MUST_BE_AUTO")
        fields.append(item)
    return tuple(fields)


class AssetIntelligenceIngestor:
    def __init__(
        self,
        repository: AssetIndexRepository,
        registry: CapabilityRegistryPort,
        analyzers: tuple[AssetAnalyzer, ...],
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._analyzers = tuple(sorted(analyzers, key=lambda item: (item.kind, item.analyzer_id)))

    def analyze_ready_asset(
        self,
        asset: VerifiedReadyAsset,
        index: AssetIndexVersion,
        *,
        analyzed_at: str,
    ) -> IngestionResult:
        if asset.state != "READY":
            return IngestionResult(None, (), "ASSET_NOT_READY")
        if asset.organization_id != index.organization_id:
            return IngestionResult(None, (), "INDEX_TENANT_MISMATCH")
        if index.state not in {"BUILDING", "READY", "ACTIVE"}:
            return IngestionResult(None, (), "INDEX_NOT_WRITABLE")

        existing = self._repository.get_analysis(
            asset.organization_id,
            asset.asset_id,
            index.index_id,
        )
        expected_id = _analysis_id(asset, index)
        if existing is not None and existing.analysis_id == expected_id and existing.state == "READY":
            return IngestionResult(existing, ("IDEMPOTENT_REUSE",))

        try:
            bundle = self._registry.resolve_analyzer_bundle(
                asset.organization_id,
                index.analyzer_version,
            )
            validate_bundle_for_index(bundle, index)
        except Exception as exc:  # adapter boundary: convert provider errors to a stable code
            return IngestionResult(None, (), f"REGISTRY_OR_INDEX_CONTRACT:{type(exc).__name__}")

        metadata: dict[str, MetadataField] = {}
        metadata = merge_metadata(
            metadata,
            system_metadata_from_asset(
                checksum_sha256=asset.checksum_sha256,
                mime_type=asset.mime_type,
                media_type=asset.media_type,
                size_bytes=asset.size_bytes,
                technical_metadata=asset.technical_metadata,
            ),
        )
        metadata = merge_metadata(metadata, user_metadata_fields(asset.user_metadata))

        ocr_blocks = []
        regions = []
        description: str | None = None
        tags: set[str] = set()
        embedding: tuple[float, ...] | None = None
        perceptual_hash: str | None = None
        language: str | None = None
        warnings: list[str] = []

        for analyzer in self._analyzers:
            try:
                output = analyzer.analyze(asset)
                metadata = merge_metadata(metadata, _auto_metadata(output))
                ocr_blocks.extend(output.ocr_blocks)
                regions.extend(output.regions)
                if output.semantic_description is not None:
                    if description is not None and description != output.semantic_description:
                        raise AssetIngestionError("MULTIPLE_VISUAL_DESCRIPTIONS")
                    description = output.semantic_description
                tags.update(tag.strip() for tag in output.visual_tags if tag.strip())
                if output.embedding is not None:
                    if embedding is not None and embedding != output.embedding:
                        raise AssetIngestionError("MULTIPLE_EMBEDDING_SPACES")
                    embedding = output.embedding
                if output.perceptual_hash is not None:
                    if perceptual_hash is not None and perceptual_hash != output.perceptual_hash:
                        raise AssetIngestionError("MULTIPLE_PERCEPTUAL_HASHES")
                    perceptual_hash = output.perceptual_hash
                if output.language is not None:
                    language = output.language
            except AssetIngestionError as exc:
                return IngestionResult(None, tuple(warnings), str(exc))
            except Exception as exc:  # optional analyzers may degrade without corrupting the index
                warnings.append(f"ANALYZER_UNAVAILABLE:{analyzer.kind}:{type(exc).__name__}")

        try:
            validate_embedding_dimensions(embedding, index)
        except Exception as exc:
            return IngestionResult(None, tuple(warnings), str(exc))

        record = AssetAnalysisRecord(
            analysis_id=expected_id,
            organization_id=asset.organization_id,
            asset_id=asset.asset_id,
            asset_version=asset.asset_version,
            project_id=asset.project_id,
            brand_id=asset.brand_id,
            index_id=index.index_id,
            index_version=index.version,
            state="READY",
            checksum_sha256=asset.checksum_sha256,
            mime_type=asset.mime_type,
            media_type=asset.media_type,
            rights=asset.rights,
            commercial_use_allowed=asset.commercial_use_allowed,
            training_authorized=asset.training_authorized,
            permission_tags=asset.permission_tags,
            preview_ref=asset.preview_ref,
            metadata=metadata,
            ocr_blocks=tuple(ocr_blocks),
            regions=tuple(regions),
            semantic_description=description,
            visual_tags=tuple(sorted(tags)),
            embedding=embedding,
            perceptual_hash=perceptual_hash,
            language=language,
            analyzer_bundle=bundle,
            created_at=analyzed_at,
        )
        self._repository.upsert_analysis(record)
        return IngestionResult(record, tuple(warnings))
