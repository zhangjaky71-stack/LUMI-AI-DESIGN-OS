from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from lumi_asset_intelligence.metadata import merge_metadata
from lumi_asset_intelligence.model import DuplicateTier, MetadataField

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures/asset-intelligence/node-45-conformance.json"
MIGRATION_PATH = ROOT / "db/migrations/0004_asset_intelligence.sql"
SEARCH_PATH = ROOT / "services/asset-intelligence/src/lumi_asset_intelligence/search.py"
REPOSITORY_PATH = ROOT / "services/asset-intelligence/src/lumi_asset_intelligence/repository.py"
MODEL_PATH = ROOT / "services/asset-intelligence/src/lumi_asset_intelligence/model.py"
INDEX_PATH = ROOT / "services/asset-intelligence/src/lumi_asset_intelligence/index_catalog.py"
RESOLVER_PATH = ROOT / "services/asset-intelligence/src/lumi_asset_intelligence/resolver.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_fixture() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assets = fixture["assets"]
    organizations = {asset["organization_id"] for asset in assets}
    require(len(organizations) >= 2, "fixture must contain a cross-tenant leak bait")
    require(any(asset["rights"] == "UNKNOWN" for asset in assets), "missing UNKNOWN rights fixture")
    require(any(asset["ocr"] for asset in assets), "missing OCR fixture")

    checksums = [asset["checksum_sha256"] for asset in assets]
    require(len(checksums) != len(set(checksums)), "fixture must contain an exact duplicate")

    index = fixture["index"]
    dimensions = int(index["embedding_dimensions"])
    require(
        all(len(asset["embedding"]) == dimensions for asset in assets),
        "fixture embedding dimensions must match the index",
    )
    require(bool(index.get("embedding_preprocessor_version")), "fixture preprocessor version missing")
    require(bool(index.get("registry_snapshot_id")), "fixture registry snapshot missing")
    require(bool(index.get("embedding_space_id")), "fixture embedding space id missing")


def validate_contracts() -> None:
    require(
        set(get_args(DuplicateTier))
        == {"EXACT", "PERCEPTUAL_NEAR_DUPLICATE", "SEMANTIC_SIMILAR"},
        "duplicate tier contract drift",
    )

    merged = merge_metadata(
        {"campaign": MetadataField("campaign", "manual", "USER", 1.0)},
        (MetadataField("campaign", "automatic", "AUTO", 0.8),),
    )
    require(merged["campaign"].value == "manual", "AUTO metadata overwrote USER metadata")

    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    required_sql = (
        "CREATE EXTENSION IF NOT EXISTS vector",
        "asset_intelligence_index_versions",
        "asset_intelligence_analysis_records",
        "asset_intelligence_ocr_blocks",
        "asset_intelligence_regions",
        "asset_intelligence_embeddings",
        "asset_intelligence_duplicate_edges",
        "asset_intelligence_usage_signals",
        "embedding_preprocessor_version text NOT NULL",
        "registry_snapshot_id text NOT NULL",
        "i.state = 'ACTIVE'",
        "organization_id = p_organization_id",
        "r.rights = ANY(p_allowed_rights)",
        "to_jsonb(p_permission_tags) @> r.permission_tags",
        "e.embedding_space_id = i.embedding_space_id",
        "e.embedding_model_id = i.embedding_model_id",
        "e.embedding_model_version = i.embedding_model_version",
        "e.preprocessor_version = i.embedding_preprocessor_version",
        "training_authorization_granted",
        "auto_delete boolean NOT NULL DEFAULT false CHECK (auto_delete = false)",
    )
    for token in required_sql:
        require(token in migration, f"missing persistence/security contract: {token}")

    search = SEARCH_PATH.read_text(encoding="utf-8")
    repository = REPOSITORY_PATH.read_text(encoding="utf-8")
    model = MODEL_PATH.read_text(encoding="utf-8")
    index_runtime = INDEX_PATH.read_text(encoding="utf-8")
    resolver = RESOLVER_PATH.read_text(encoding="utf-8")

    scoped_position = search.index("scoped_candidates")
    scoring_position = search.index("for record in candidates")
    require(scoped_position < scoring_position, "scoring must happen after scoped candidate retrieval")
    require("._records" not in search, "search engine may not bypass scoped repository retrieval")
    require("_scope_allows" in repository, "repository is missing pre-retrieval access filtering")
    require("filename" not in search.casefold(), "search ranking must not guess from filenames")
    require("filename" not in resolver.casefold(), "resolver must not guess from filenames")
    require("commercial_use_allowed" in model, "commercial rights metadata missing")
    require("training_authorized" in model, "training authorization must be modeled separately")
    require("embedding_space_id" in model, "embedding space version pin missing")
    require("embedding_preprocessor_version" in model, "embedding preprocessor pin missing")
    require("registry_snapshot_id" in model, "registry snapshot pin missing")
    require("embedding_space_changed" in index_runtime, "reindex comparison missing space change evidence")
    require("persistent_biometric" not in migration.casefold(), "NODE-45 must not create biometric indexes")


def main() -> None:
    validate_fixture()
    validate_contracts()
    print("NODE-45 asset intelligence contract: OK")


if __name__ == "__main__":
    main()
