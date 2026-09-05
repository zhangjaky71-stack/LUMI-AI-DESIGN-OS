from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from lumi_domain.design_ir_canonical import hash_document
from lumi_domain.design_ir_document import parse_document, query_nodes, validate_document

FIXTURE_PATH = Path(__file__).parents[3] / "fixtures/design-ir/node-38-conformance.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_and_query_document() -> None:
    source = FIXTURE["document"]
    parsed = parse_document(source)
    assert parsed is not source
    assert validate_document(parsed) == {"valid": True, "issues": []}
    assert [node["id"] for node in query_nodes(parsed, {"kinds": ["TEXT"]})] == ["headline"]


def test_cycle_is_rejected() -> None:
    document = deepcopy(FIXTURE["document"])
    document["nodes"]["root"]["parent_id"] = "headline"
    document["nodes"]["headline"]["children"].append("root")
    result = validate_document(document)
    assert result["valid"] is False
    assert any(issue["code"] == "IR_GRAPH_CYCLE" for issue in result["issues"])


def test_document_hash_normalizes_unicode_and_ignores_ephemeral_metadata() -> None:
    left = deepcopy(FIXTURE["document"])
    right = deepcopy(FIXTURE["document"])
    left["metadata"]["viewport"] = {"x": 1, "y": 2}
    right["metadata"]["viewport"] = {"x": 999, "y": 999}
    left["nodes"]["headline"]["content"] = "Cafe\u0301"
    right["nodes"]["headline"]["content"] = "Café"
    assert hash_document(left) == hash_document(right)
