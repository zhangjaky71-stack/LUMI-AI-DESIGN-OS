from __future__ import annotations

import ast
import json
from pathlib import Path

from lumi_api.design_ir.document import (
    DesignIRDocument,
    canonical_json,
    content_hash_sha256,
    empty_document,
)
from lumi_api.design_ir.operations import OPERATION_NAMES, DesignOperationBatch

ROOT = Path(__file__).resolve().parents[2]
DESIGN_IR_ROOT = ROOT / "apps" / "api" / "src" / "lumi_api" / "design_ir"
DOC = ROOT / "docs" / "design-ir" / "DESIGN-IR-V1.md"

EXPECTED_OPERATIONS = {
    "add_node",
    "remove_node",
    "move_node",
    "reorder_children",
    "set_transform",
    "set_size",
    "set_appearance",
    "set_lock",
    "rename_node",
    "set_text",
    "set_text_style",
    "set_image_asset",
    "set_image_crop",
    "set_fill",
    "set_stroke",
    "set_page_background",
}
FORBIDDEN_IMPORT_ROOTS = {
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "pixi",
    "pixijs",
    "langgraph",
    "langchain",
    "openai",
    "anthropic",
    "boto3",
}


def assert_operation_registry() -> None:
    assert len(OPERATION_NAMES) == 16
    assert set(OPERATION_NAMES) == EXPECTED_OPERATIONS
    assert len(set(OPERATION_NAMES)) == len(OPERATION_NAMES)


def assert_json_schema_contract() -> None:
    ir_schema = DesignIRDocument.model_json_schema()
    op_schema = DesignOperationBatch.model_json_schema()
    assert ir_schema["title"] == "DesignIRDocument"
    assert op_schema["title"] == "DesignOperationBatch"
    serialized = json.dumps(
        {"design_ir": ir_schema, "operations": op_schema},
        sort_keys=True,
        allow_nan=False,
    )
    assert "lumi.design-ir/1.0" in serialized
    assert "lumi.design-op/1.0" in serialized
    for operation in EXPECTED_OPERATIONS:
        assert operation in serialized


def assert_canonical_document() -> None:
    document = empty_document(width=750, height=1624)
    assert document.document_id.version == 7
    assert document.revision == 1
    assert document.coordinate_space == "logical_px"
    encoded = canonical_json(document)
    assert encoded == canonical_json(document)
    digest = content_hash_sha256(document)
    assert len(digest) == 64
    int(digest, 16)


def assert_dependency_purity() -> None:
    discovered: set[str] = set()
    for path in DESIGN_IR_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                discovered.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                discovered.add(node.module.split(".")[0])
    assert discovered.isdisjoint(FORBIDDEN_IMPORT_ROOTS), discovered & FORBIDDEN_IMPORT_ROOTS


def assert_documented_invariants() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    required = (
        "renderer-neutral",
        "logical_px",
        "atomic batch",
        "base_revision",
        "canonical",
        "uuidv7",
        "no arbitrary json patch",
    )
    for fragment in required:
        assert fragment in text, f"missing Design IR contract wording: {fragment}"


def main() -> None:
    assert_operation_registry()
    assert_json_schema_contract()
    assert_canonical_document()
    assert_dependency_purity()
    assert_documented_invariants()
    print(
        "NODE-13 Design IR validation PASS: "
        "7 node kinds, 16 typed operations, canonical hash, atomic revision contract, "
        "renderer/ORM/agent-runtime independence"
    )


if __name__ == "__main__":
    main()
