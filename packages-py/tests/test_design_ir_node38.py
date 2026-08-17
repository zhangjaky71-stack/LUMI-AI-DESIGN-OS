from __future__ import annotations

import json
import random
import time
from copy import deepcopy
from pathlib import Path

import pytest

from design_ir import (
    CommandHistory,
    IrIssue,
    IrRuntimeError,
    apply_batch,
    apply_operation,
    canonicalize,
    compute_semantic_diff,
    hash_document,
    migrate,
    parse_document,
    query_nodes,
    validate_document,
)

FIXTURES = Path(__file__).parents[2] / "packages" / "design-ir" / "fixtures" / "conformance-v1.json"
PAYLOAD = json.loads(FIXTURES.read_text(encoding="utf-8"))
BASE = PAYLOAD["fixtures"][0]["document"]


def test_shared_canonical_hash_fixtures() -> None:
    for fixture in PAYLOAD["fixtures"]:
        assert canonicalize(fixture["document"]) == fixture["canonical"]
        assert hash_document(fixture["document"]) == fixture["sha256"]


def test_parse_validate_roundtrip_is_stable() -> None:
    parsed = parse_document(BASE)
    reparsed = parse_document(json.loads(json.dumps(parsed, ensure_ascii=False)))
    assert reparsed == parsed
    assert validate_document(parsed) == []


def test_operation_is_copy_on_write_and_increments_version() -> None:
    before = deepcopy(BASE)
    result = apply_operation(
        BASE,
        {
            "operation_id": "py-set-text",
            "type": "SET_TEXT",
            "target_ids": ["headline"],
            "expected_document_version": 7,
            "payload": {"content": "Python 标题"},
        },
    )
    assert BASE == before
    assert result.document["nodes"]["headline"]["content"] == "Python 标题"
    assert result.document_version == 8
    assert result.diff["text_changed"] == ["headline"]


def test_version_conflict() -> None:
    with pytest.raises(IrRuntimeError, match="IR_VERSION_CONFLICT"):
        apply_operation(
            BASE,
            {
                "operation_id": "conflict",
                "type": "SET_TEXT",
                "target_ids": ["headline"],
                "expected_document_version": 2,
                "payload": {"content": "x"},
            },
        )


def test_batch_is_atomic() -> None:
    operations = [
        {
            "operation_id": "move",
            "type": "MOVE_NODE",
            "target_ids": ["hero"],
            "expected_document_version": 7,
            "payload": {"x": 100, "y": 400},
        },
        {
            "operation_id": "bad",
            "type": "SET_TEXT",
            "target_ids": ["hero"],
            "expected_document_version": 7,
            "payload": {"content": "bad"},
        },
    ]
    before = deepcopy(BASE)
    with pytest.raises(IrRuntimeError, match="IR_BATCH_FAILED"):
        apply_batch(BASE, operations, 7, "atomic")
    assert BASE == before


def test_constraint_preflight_aborts_before_write() -> None:
    def preflight(_document: dict, operation: dict) -> list[IrIssue]:
        if operation["payload"].get("x") == -10:
            return [IrIssue("IR_CONSTRAINT_FAILED", "protected region")]
        return []

    with pytest.raises(IrRuntimeError, match="IR_CONSTRAINT_FAILED"):
        apply_operation(
            BASE,
            {
                "operation_id": "constraint",
                "type": "MOVE_NODE",
                "target_ids": ["hero"],
                "expected_document_version": 7,
                "payload": {"x": -10, "y": 10},
            },
            preflight,
        )


def test_query_selectors() -> None:
    assert [node["id"] for node in query_nodes(BASE, {"role": "HEADLINE"})] == ["headline"]
    assert [node["id"] for node in query_nodes(BASE, {"asset_binding": "asset:coffee-001"})] == [
        "hero"
    ]
    assert sorted(node["id"] for node in query_nodes(BASE, {"frame_id": "frame"})) == [
        "frame",
        "headline",
        "hero",
    ]


def test_semantic_diff_asset_replace() -> None:
    result = apply_operation(
        BASE,
        {
            "operation_id": "asset",
            "type": "REPLACE_ASSET",
            "target_ids": ["hero"],
            "expected_document_version": 7,
            "payload": {"asset_id": "asset:coffee-002"},
        },
    )
    assert result.diff["asset_replaced"] == ["hero"]
    assert compute_semantic_diff(BASE, result.document)["asset_replaced"] == ["hero"]


def test_migration_chain_and_provenance() -> None:
    migrated = migrate(BASE, "2.0")
    assert migrated["schema_version"] == "2.0"
    assert len(migrated["metadata"]["migration_provenance"]) == 2


def test_command_history() -> None:
    execution = apply_operation(
        BASE,
        {
            "operation_id": "history",
            "type": "SET_TEXT",
            "target_ids": ["headline"],
            "expected_document_version": 7,
            "payload": {"content": "history"},
        },
    )
    history = CommandHistory()
    history.push(BASE, execution)
    assert history.undo(execution.document)["nodes"]["headline"]["content"] == "Café 新品"
    assert history.redo(BASE)["nodes"]["headline"]["content"] == "history"


def test_invalid_float_rejected() -> None:
    invalid = deepcopy(BASE)
    invalid["nodes"]["hero"]["transform"]["x"] = float("nan")
    assert validate_document(invalid)[0].code == "IR_SCHEMA_INVALID"


def test_random_reorders_preserve_graph_invariant() -> None:
    rng = random.Random(38)
    document = deepcopy(BASE)
    for index in range(100):
        target = rng.choice(["headline", "hero"])
        version = document["metadata"]["document_version"]
        document = apply_operation(
            document,
            {
                "operation_id": f"reorder-{index}",
                "type": "REORDER_NODE",
                "target_ids": [target],
                "expected_document_version": version,
                "payload": {"index": rng.randint(0, 2)},
            },
        ).document
        assert validate_document(document) == []


def test_reference_benchmark_2k_and_batch_100(capsys: pytest.CaptureFixture[str]) -> None:
    nodes: dict[str, dict] = {
        "root": {"id": "root", "kind": "DOCUMENT_ROOT", "parent_id": None, "children": ["frame"]},
        "frame": {
            "id": "frame",
            "kind": "FRAME",
            "parent_id": "root",
            "children": [f"n{i}" for i in range(2000)],
        },
    }
    for i in range(2000):
        nodes[f"n{i}"] = {
            "id": f"n{i}",
            "kind": "TEXT",
            "parent_id": "frame",
            "children": [],
            "content": f"node-{i}",
            "transform": {"x": i % 100, "y": i // 100, "width": 20, "height": 10},
        }
    document = {
        "schema_version": "1.0",
        "document_id": "benchmark-2k",
        "unit": "px",
        "root_id": "root",
        "nodes": nodes,
        "resources": {},
        "metadata": {"document_version": 0},
    }
    started = time.perf_counter()
    parse_document(document)
    parse_ms = (time.perf_counter() - started) * 1000
    operations = [
        {
            "operation_id": f"bench-{i}",
            "type": "MOVE_NODE",
            "target_ids": [f"n{i}"],
            "expected_document_version": 0,
            "payload": {"x": i, "y": i + 1},
        }
        for i in range(100)
    ]
    started = time.perf_counter()
    result = apply_batch(document, operations, 0, "benchmark-batch")
    batch_ms = (time.perf_counter() - started) * 1000
    assert result.document_version == 1
    assert parse_ms < 5000
    assert batch_ms < 5000
    print(f"NODE38_BENCH parse_2k_ms={parse_ms:.3f} batch_100_ms={batch_ms:.3f}")
