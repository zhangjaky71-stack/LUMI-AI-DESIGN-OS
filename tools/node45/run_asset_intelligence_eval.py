from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from lumi_asset_intelligence import (
    AccessScope,
    AssetAnalysisRecord,
    AssetIndexVersion,
    AssetSearchEngine,
    AssetSearchRequest,
    BoundingBox,
    DuplicatePolicy,
    InMemoryAssetIndexRepository,
    MetadataField,
    OcrSpan,
    classify_similarity,
)

ORG = UUID("11111111-1111-4111-8111-111111111111")
INDEX = UUID("22222222-2222-4222-8222-222222222222")
REGISTRY = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _record(raw: dict[str, object]) -> AssetAnalysisRecord:
    aid = UUID(str(raw["id"]))
    ocr_text = str(raw["ocr"])
    ocr = (
        OcrSpan(
            text=ocr_text,
            confidence=1.0,
            bbox=BoundingBox(0, 0, 1, 1),
            analyzer_id="fixture",
            analyzer_version="1",
        ),
    ) if ocr_text else ()
    return AssetAnalysisRecord(
        id=UUID(int=aid.int ^ 17),
        organization_id=ORG,
        asset_id=aid,
        asset_version=str(raw["checksum"]),
        project_id=None,
        brand_id=None,
        index_id=INDEX,
        index_version=1,
        state="READY",
        checksum_sha256=str(raw["checksum"]),
        source="fixture",
        mime_type="image/png",
        media_kind="image",
        rights_level=str(raw["rights"]),  # type: ignore[arg-type]
        commercial_use=bool(raw["commercial"]),
        training_authorized=False,
        permission_tags=tuple(str(v) for v in raw["permission_tags"]),  # type: ignore[union-attr]
        preview_ref=None,
        metadata={
            "name": MetadataField(key="name", value=raw["name"], source="USER")
        },
        ocr_spans=ocr,
        regions=(),
        semantic_description=str(raw["description"]),
        visual_tags=tuple(str(v) for v in raw["tags"]),  # type: ignore[union-attr]
        embedding=tuple(float(v) for v in raw["embedding"]),  # type: ignore[union-attr]
        perceptual_hash=str(raw["phash"]),
        language="en",
        local_signature=(),
        color_signature=(),
        brand_region_signature=(),
        analyzer_version="fixture-v1",
        embedding_model_key="fixture/embed",
        embedding_revision_key="fixture/embed@1",
        embedding_version="1",
        registry_version_id=REGISTRY,
        evidence_refs=(),
        created_at=NOW,
    )


def main() -> None:
    payload = json.loads(
        Path("evals/node45/asset-intelligence-fixtures.json").read_text(encoding="utf-8")
    )
    repo = InMemoryAssetIndexRepository()
    index = AssetIndexVersion(
        id=INDEX,
        organization_id=ORG,
        version=1,
        analyzer_version="fixture-v1",
        embedding_model_key="fixture/embed",
        embedding_revision_key="fixture/embed@1",
        embedding_version="1",
        embedding_dimensions=4,
        embedding_space_id="fixture:1:4",
        registry_version_id=REGISTRY,
        state="ACTIVE",
        created_at=NOW,
        activated_at=NOW,
        coverage_count=len(payload["assets"]),
    )
    repo.create_index(index)
    repo._active[ORG] = INDEX
    records: dict[str, AssetAnalysisRecord] = {}
    for raw in payload["assets"]:
        value = _record(raw)
        records[str(value.asset_id)] = value
        repo.upsert_analysis(value)

    engine = AssetSearchEngine(repo)
    passed = 0
    for case in payload["queries"]:
        rights = ("unknown", "owned", "licensed", "public_domain", "restricted")
        if case.get("commercial"):
            rights = ("owned", "licensed", "public_domain")
        request = AssetSearchRequest(
            scope=AccessScope(
                organization_id=ORG,
                permission_tags=tuple(case.get("permission_tags", [])),
                allowed_rights=rights,
                commercial_use=bool(case.get("commercial", False)),
            ),
            query=case["query"],
            mode=case["mode"],
            query_embedding=(
                tuple(case["query_embedding"]) if "query_embedding" in case else None
            ),
        )
        hits = engine.search(request, index)
        if "expected_top" in case:
            assert hits and str(hits[0].asset_id) == case["expected_top"], case["case"]
        else:
            assert len(hits) == case["expected_count"], case["case"]
        passed += 1

    policy = DuplicatePolicy("fixture-v1", 2, 0.95)
    for case in payload["duplicates"]:
        evidence = classify_similarity(
            records[case["source"]], records[case["candidate"]], policy
        )
        assert [item.tier for item in evidence] == case["expected"], case["case"]
        passed += 1
    print(f"NODE45_ASSET_INTELLIGENCE_EVAL_PASS cases={passed}")


if __name__ == "__main__":
    main()
