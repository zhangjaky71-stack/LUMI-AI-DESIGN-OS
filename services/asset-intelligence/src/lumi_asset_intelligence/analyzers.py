from __future__ import annotations

from dataclasses import dataclass

from .model import (
    AnalyzerBundleSnapshot,
    AnalyzerKind,
    AnalyzerOutput,
    AssetAnalyzer,
    AssetIndexVersion,
    VerifiedReadyAsset,
)


class AnalyzerContractError(ValueError):
    pass


@dataclass(frozen=True)
class FixtureAnalyzer(AssetAnalyzer):
    """Deterministic conformance adapter. It is not a production OCR/VLM model."""

    analyzer_id: str
    analyzer_version: str
    kind: AnalyzerKind
    outputs: dict[str, AnalyzerOutput]

    def analyze(self, asset: VerifiedReadyAsset) -> AnalyzerOutput:
        return self.outputs.get(asset.asset_id, AnalyzerOutput())


@dataclass(frozen=True)
class StaticCapabilityRegistry:
    """Conformance implementation of the NODE-23 registry port."""

    bundles: dict[tuple[str, str], AnalyzerBundleSnapshot]

    def resolve_analyzer_bundle(
        self,
        organization_id: str,
        analyzer_version: str,
    ) -> AnalyzerBundleSnapshot:
        key = (organization_id, analyzer_version)
        try:
            return self.bundles[key]
        except KeyError as exc:
            raise AnalyzerContractError("ANALYZER_BUNDLE_NOT_REGISTERED") from exc


def validate_bundle_for_index(
    bundle: AnalyzerBundleSnapshot,
    index: AssetIndexVersion,
) -> None:
    if bundle.analyzer_version != index.analyzer_version:
        raise AnalyzerContractError("ANALYZER_VERSION_MISMATCH")
    embedding = bundle.embedding
    if embedding is None:
        raise AnalyzerContractError("EMBEDDING_CAPABILITY_UNAVAILABLE")
    if embedding.model_id != index.embedding_model_id:
        raise AnalyzerContractError("EMBEDDING_MODEL_MISMATCH")
    if embedding.model_version != index.embedding_model_version:
        raise AnalyzerContractError("EMBEDDING_MODEL_VERSION_MISMATCH")
    if embedding.preprocessor_version != index.embedding_preprocessor_version:
        raise AnalyzerContractError("EMBEDDING_PREPROCESSOR_VERSION_MISMATCH")
    if embedding.registry_snapshot_id != index.registry_snapshot_id:
        raise AnalyzerContractError("REGISTRY_SNAPSHOT_MISMATCH")


def validate_embedding_dimensions(
    embedding: tuple[float, ...] | None,
    index: AssetIndexVersion,
) -> None:
    if embedding is None:
        raise AnalyzerContractError("EMBEDDING_REQUIRED_FOR_INDEX")
    if len(embedding) != index.embedding_dimensions:
        raise AnalyzerContractError("EMBEDDING_DIMENSION_MISMATCH")
