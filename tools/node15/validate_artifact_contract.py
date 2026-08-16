from __future__ import annotations

import ast
import json
from pathlib import Path

from lumi_api.artifacts.models import (
    ArtifactType,
    ArtifactVersionStatus,
    FileRole,
    LineageEdgeType,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "apps" / "api" / "src" / "lumi_api" / "artifacts"
PERSISTENCE = ROOT / "apps" / "api" / "src" / "lumi_api" / "persistence" / "models_artifacts.py"
GAPS = ROOT / "reports" / "nodes" / "NODE-15" / "persistence-gap-ledger.json"
FIXTURES = ROOT / "benchmarks" / "artifacts" / "lineage-fixtures-v1.jsonl"

FORBIDDEN_IMPORT_PREFIXES = (
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "langgraph",
    "langchain",
    "openai",
    "anthropic",
    "boto3",
    "redis",
    "celery",
    "PIL",
    "cv2",
)

EXPECTED_ARTIFACT_TYPES = {
    "DESIGN_DOCUMENT",
    "RASTER_IMAGE",
    "VECTOR_IMAGE",
    "VIDEO",
    "AUDIO",
    "PDF",
    "HTML",
    "ARCHIVE",
    "EXPORT_PACKAGE",
}
EXPECTED_STATUSES = {"DRAFT", "READY", "APPROVED", "REJECTED", "ARCHIVED"}
EXPECTED_EDGE_TYPES = {
    "DERIVED_FROM",
    "EDITED_FROM",
    "GENERATED_FROM",
    "COMPOSED_FROM",
    "RESIZED_FROM",
    "EXPORTED_FROM",
    "REFERENCE_USED",
}
EXPECTED_FILE_ROLES = {
    "preview",
    "original",
    "thumbnail",
    "web-optimized",
    "print-pdf",
    "layer-data",
}
EXPECTED_GAPS = {f"PERSIST-15-{index:02d}" for index in range(1, 11)}
REQUIRED_PERSISTENCE_TABLE_MARKERS = {
    '__tablename__ = "artifacts"',
    '__tablename__ = "artifact_branches"',
    '__tablename__ = "artifact_versions"',
    '__tablename__ = "artifact_edges"',
    '__tablename__ = "artifact_files"',
    '__tablename__ = "artifact_provenance"',
}


def validate_import_boundaries() -> None:
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    raise SystemExit(
                        f"forbidden Artifact contract dependency {module!r} in {path}"
                    )


def validate_frozen_enums() -> None:
    if {item.value for item in ArtifactType} != EXPECTED_ARTIFACT_TYPES:
        raise SystemExit("ArtifactType registry does not match NODE-15 contract")
    if {item.value for item in ArtifactVersionStatus} != EXPECTED_STATUSES:
        raise SystemExit("ArtifactVersionStatus registry does not match NODE-15 contract")
    if {item.value for item in LineageEdgeType} != EXPECTED_EDGE_TYPES:
        raise SystemExit("LineageEdgeType registry does not match NODE-15 contract")
    if {item.value for item in FileRole} != EXPECTED_FILE_ROLES:
        raise SystemExit("FileRole registry does not match NODE-15 contract")


def validate_persistence_gap_ledger() -> None:
    persistence_text = PERSISTENCE.read_text(encoding="utf-8")
    missing_tables = sorted(
        marker for marker in REQUIRED_PERSISTENCE_TABLE_MARKERS if marker not in persistence_text
    )
    if missing_tables:
        raise SystemExit(f"NODE-10 artifact persistence baseline changed: {missing_tables}")
    ledger = json.loads(GAPS.read_text(encoding="utf-8"))
    gap_ids = {item["id"] for item in ledger["gaps"]}
    if gap_ids != EXPECTED_GAPS:
        raise SystemExit(
            f"NODE-15 persistence gap ledger mismatch missing={sorted(EXPECTED_GAPS-gap_ids)} "
            f"extra={sorted(gap_ids-EXPECTED_GAPS)}"
        )
    if ledger["status"] != "TRACKED_CONTRACT_GAPS":
        raise SystemExit("persistence gap ledger must remain explicitly non-closed")


def validate_lineage_fixtures() -> None:
    rows = [
        json.loads(line)
        for line in FIXTURES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) < 20:
        raise SystemExit(f"NODE-15 lineage fixtures require >=20 rows, got {len(rows)}")
    ids = [row["case_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("NODE-15 lineage fixture case_id values must be unique")
    required_categories = {
        "version_immutability",
        "fork",
        "restore",
        "multi_parent",
        "cross_tenant",
        "cycle",
        "rights",
        "manifest",
        "gc",
    }
    actual_categories = {row["category"] for row in rows}
    if not required_categories.issubset(actual_categories):
        raise SystemExit(
            "NODE-15 lineage fixtures missing categories: "
            + ",".join(sorted(required_categories - actual_categories))
        )


def main() -> None:
    validate_import_boundaries()
    validate_frozen_enums()
    validate_persistence_gap_ledger()
    validate_lineage_fixtures()
    print("NODE15_ARTIFACT_CONTRACT_VALIDATION_PASS")
    print(f"artifact_types={len(ArtifactType)}")
    print(f"lineage_edge_types={len(LineageEdgeType)}")
    print(f"tracked_persistence_gaps={len(EXPECTED_GAPS)}")
    print("lineage_fixtures>=20")


if __name__ == "__main__":
    main()
