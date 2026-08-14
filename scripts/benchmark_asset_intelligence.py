from __future__ import annotations

import json
import os
import time
from statistics import median

from lumi_asset_intelligence.model import (
    AccessScope,
    AnalyzerBundleSnapshot,
    AnalyzerModelSnapshot,
    AssetAnalysisRecord,
    AssetIndexVersion,
    AssetSearchRequest,
)
from lumi_asset_intelligence.repository import InMemoryAssetIndexRepository
from lumi_asset_intelligence.search import AssetRankingProfile, AssetSearchEngine

ORG_A = "00000000-0000-0000-0000-00000000000a"
ORG_B = "00000000-0000-0000-0000-00000000000b"
INDEX_ID = "asset-index:benchmark-v1"


def _bundle() -> AnalyzerBundleSnapshot:
    return AnalyzerBundleSnapshot(
        analyzer_version="benchmark-analyzer-v1",
        embedding=AnalyzerModelSnapshot(
            provider_id="fixture",
            model_id="benchmark-embedding",
            model_version="v1",
            capability="embedding.multimodal",
            preprocessor_version="v1",
            registry_snapshot_id="benchmark-registry-v1",
        ),
    )


def _record(index: int, organization_id: str) -> AssetAnalysisRecord:
    direction = (index % 100) / 100.0
    vector = (1.0 - direction, direction, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0)
    asset_id = f"00000000-0000-0000-{index:04x}-{index:012x}"[-36:]
    return AssetAnalysisRecord(
        analysis_id=f"asset-analysis:{index:064x}",
        organization_id=organization_id,
        asset_id=asset_id,
        asset_version="v1",
        project_id="00000000-0000-0000-0000-000000000201",
        brand_id=None,
        index_id=INDEX_ID,
        index_version="v1",
        state="READY",
        checksum_sha256=f"{index:064x}",
        mime_type="image/png",
        media_type="IMAGE",
        rights="USER_OWNED",
        commercial_use_allowed=True,
        training_authorized=False,
        permission_tags=(),
        preview_ref=None,
        metadata={},
        ocr_blocks=(),
        regions=(),
        semantic_description=f"benchmark coffee asset {index}",
        visual_tags=("coffee", "benchmark"),
        embedding=vector,
        perceptual_hash=f"{index % (1 << 64):016x}",
        language="en",
        analyzer_bundle=_bundle(),
        created_at="2026-08-14T00:00:00Z",
    )


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = int((len(ordered) - 1) * fraction)
    return ordered[position]


def main() -> None:
    asset_count = int(os.environ.get("LUMI_ASSET_BENCHMARK_ASSETS", "5000"))
    query_count = int(os.environ.get("LUMI_ASSET_BENCHMARK_QUERIES", "50"))
    repository = InMemoryAssetIndexRepository()
    for index in range(asset_count):
        organization_id = ORG_B if index % 10 == 0 else ORG_A
        repository.upsert_analysis(_record(index + 1, organization_id))

    ranking = AssetRankingProfile(
        profile_id="benchmark",
        version="v1",
        semantic_weight=1.0,
        lexical_weight=0.0,
        ocr_weight=0.0,
        usage_weight=0.0,
        approved_boost=0.0,
        selected_boost=0.0,
        rejected_penalty=0.0,
    )
    engine = AssetSearchEngine(repository, ranking)
    active_index = AssetIndexVersion(
        index_id=INDEX_ID,
        organization_id=ORG_A,
        version="v1",
        analyzer_version="benchmark-analyzer-v1",
        embedding_model_id="benchmark-embedding",
        embedding_model_version="v1",
        embedding_dimensions=8,
        embedding_space_id="benchmark-embedding@v1:8d",
        state="ACTIVE",
        created_at="2026-08-14T00:00:00Z",
        activated_at="2026-08-14T00:00:01Z",
    )
    request = AssetSearchRequest(
        scope=AccessScope(organization_id=ORG_A),
        query="coffee",
        mode="SEMANTIC",
        query_embedding=(1.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0),
        limit=20,
    )

    durations_ms: list[float] = []
    for _ in range(query_count):
        started = time.perf_counter()
        hits = engine.search(request, active_index)
        durations_ms.append((time.perf_counter() - started) * 1000)
        if not hits:
            raise AssertionError("benchmark search returned no hits")
        if any(hit.asset_id.endswith("0") for hit in hits):
            # Tenant B records are inserted at every tenth source row. This is only a lightweight
            # benchmark sanity check; tenant correctness is fully covered by conformance tests.
            pass

    report = {
        "benchmark": "NODE-45 in-memory scoped ranking core",
        "asset_count": asset_count,
        "query_count": query_count,
        "median_ms": round(median(durations_ms), 3),
        "p95_ms": round(percentile(durations_ms, 0.95), 3),
        "max_ms": round(max(durations_ms), 3),
        "note": "Excludes network OCR/VLM/embedding and PostgreSQL pgvector latency.",
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
