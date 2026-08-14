from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from lumi_domain.design_ir_runtime import (
    DesignIrMigrationRegistry,
    canonical_json,
    canonical_sha256,
    execute_operations,
    semantic_diff,
)

FIXTURE_PATH = Path(__file__).parents[3] / "fixtures/design-ir/node-38-conformance.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_cross_runtime_canonical_vectors() -> None:
    document = FIXTURE["document"]
    assert canonical_sha256(document) == FIXTURE["expected_input_sha256"]
    result = execute_operations(document, FIXTURE["operations"])
    assert result["ok"] is True
    assert canonical_sha256(result["document"]) == FIXTURE["expected_output_sha256"]


def test_runtime_is_immutable_and_deterministic() -> None:
    source = FIXTURE["document"]
    original = canonical_json(source)
    outputs = {
        canonical_json(execute_operations(deepcopy(source), deepcopy(FIXTURE["operations"]))["document"])
        for _ in range(50)
    }
    assert len(outputs) == 1
    assert canonical_json(source) == original


def test_atomic_failure_returns_original_document() -> None:
    source = FIXTURE["document"]
    operations = [
        FIXTURE["operations"][0],
        {
            "operation_id": "missing-target",
            "type": "SET_TEXT",
            "target_ids": ["does-not-exist"],
            "expected_document_version": 7,
            "payload": {"content": "must roll back"},
        },
    ]
    result = execute_operations(source, operations)
    assert result["ok"] is False
    assert result["document"] is source
    assert result["failures"][0]["code"] == "TARGET_NOT_FOUND"
    assert canonical_json(result["document"]) == canonical_json(source)


def test_version_conflict_fails_closed() -> None:
    operation = deepcopy(FIXTURE["operations"][0])
    operation["expected_document_version"] = 6
    result = execute_operations(FIXTURE["document"], [operation])
    assert result["ok"] is False
    assert result["failures"][0]["code"] == "VERSION_CONFLICT"


def test_semantic_diff_reports_text_and_geometry() -> None:
    result = execute_operations(FIXTURE["document"], FIXTURE["operations"])
    diff = semantic_diff(FIXTURE["document"], result["document"])
    kinds = {change["kind"] for change in diff["changes"]}
    assert diff["changed"] is True
    assert "headline" in diff["changed_node_ids"]
    assert {"TEXT_CHANGED", "GEOMETRY_CHANGED"} <= kinds


def test_migration_preserves_provenance() -> None:
    registry = DesignIrMigrationRegistry()

    def migrate(document: dict[str, object]) -> dict[str, object]:
        document["schema_version"] = "1.1"
        metadata = document.get("metadata")
        assert isinstance(metadata, dict)
        metadata.pop("provenance", None)
        return document

    registry.register("1.0", "1.1", migrate)
    migrated = registry.migrate(FIXTURE["document"], "1.1")
    assert migrated["schema_version"] == "1.1"
    assert migrated["metadata"]["provenance"] == FIXTURE["document"]["metadata"]["provenance"]
