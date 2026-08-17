from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages-py"))

from design_ir import (  # noqa: E402
    apply_batch,
    hash_document,
    migrate,
    parse_document,
    query_nodes,
)

REQUIRED = (
    "packages/design-ir/src/types.ts",
    "packages/design-ir/src/validation.ts",
    "packages/design-ir/src/canonical.ts",
    "packages/design-ir/src/query.ts",
    "packages/design-ir/src/diff.ts",
    "packages/design-ir/src/migrations.ts",
    "packages/design-ir/src/executor.ts",
    "packages/design-ir/src/history.ts",
    "packages/design-ir/src/index.ts",
    "packages/design-ir/tests/runtime.node38.test.ts",
    "packages/design-ir/fixtures/conformance-v1.json",
    "packages-py/design_ir/__init__.py",
    "packages-py/design_ir/models.py",
    "packages-py/design_ir/validate.py",
    "packages-py/design_ir/canonical.py",
    "packages-py/design_ir/query.py",
    "packages-py/design_ir/diff.py",
    "packages-py/design_ir/migrations.py",
    "packages-py/design_ir/operations.py",
    "packages-py/design_ir/history.py",
    "packages-py/tests/test_design_ir_node38.py",
    "reports/nodes/NODE-38/gap-ledger.json",
)

FORBIDDEN_TS = ("pixi", "react", "openai", "anthropic")
FORBIDDEN_PY = ("openai", "anthropic", "langchain", "langgraph")


def _require_files() -> None:
    missing = [path for path in REQUIRED if not (REPO / path).exists()]
    if missing:
        raise SystemExit("NODE38_REQUIRED_FILES_MISSING:" + ",".join(missing))


def _assert_boundaries() -> None:
    ts_source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (REPO / "packages/design-ir/src").glob("*.ts")
    )
    for token in FORBIDDEN_TS:
        if f'from "{token}' in ts_source or f"from '{token}" in ts_source:
            raise SystemExit(f"NODE38_FORBIDDEN_TS_IMPORT:{token}")
    py_source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (REPO / "packages-py/design_ir").glob("*.py")
    )
    for token in FORBIDDEN_PY:
        if f"import {token}" in py_source or f"from {token}" in py_source:
            raise SystemExit(f"NODE38_FORBIDDEN_PY_IMPORT:{token}")


def _assert_runtime_contract() -> None:
    payload = json.loads(
        (REPO / "packages/design-ir/fixtures/conformance-v1.json").read_text(encoding="utf-8")
    )
    assert payload["schema"] == "lumi.design-ir.conformance.v1"
    assert len(payload["fixtures"]) >= 4
    for fixture in payload["fixtures"]:
        document = parse_document(fixture["document"])
        assert hash_document(document) == fixture["sha256"]

    base = payload["fixtures"][0]["document"]
    assert [item["id"] for item in query_nodes(base, {"role": "HEADLINE"})] == ["headline"]
    migrated = migrate(base, "2.0")
    assert migrated["schema_version"] == "2.0"

    operations = [
        {
            "operation_id": "validator-move",
            "type": "MOVE_NODE",
            "target_ids": ["hero"],
            "expected_document_version": 7,
            "payload": {"x": 101, "y": 401},
        },
        {
            "operation_id": "validator-text",
            "type": "SET_TEXT",
            "target_ids": ["headline"],
            "expected_document_version": 7,
            "payload": {"content": "validator"},
        },
    ]
    result = apply_batch(base, operations, 7, "validator-batch")
    assert result.document_version == 8
    assert result.diff["geometry_changed"] == ["hero"]
    assert result.diff["text_changed"] == ["headline"]

    ledger = json.loads(
        (REPO / "reports/nodes/NODE-38/gap-ledger.json").read_text(encoding="utf-8")
    )
    assert ledger["node"] == "NODE-38"
    assert len(ledger["gaps"]) == 5


def _assert_ts_surface() -> None:
    index = (REPO / "packages/design-ir/src/index.ts").read_text(encoding="utf-8")
    executor = (REPO / "packages/design-ir/src/executor.ts").read_text(encoding="utf-8")
    canonical = (REPO / "packages/design-ir/src/canonical.ts").read_text(encoding="utf-8")
    required_tokens = (
        "applyOperation",
        "applyBatch",
        "IR_VERSION_CONFLICT",
        "IR_BATCH_FAILED",
        "validateDocument",
    )
    combined = index + executor + canonical + (
        REPO / "packages/design-ir/src/validation.ts"
    ).read_text(encoding="utf-8")
    for token in required_tokens:
        if token not in combined:
            raise SystemExit(f"NODE38_TS_SURFACE_MISSING:{token}")


def main() -> None:
    _require_files()
    _assert_boundaries()
    _assert_runtime_contract()
    _assert_ts_surface()
    print("NODE38_DESIGN_IR_RUNTIME_VALIDATION_PASS")


if __name__ == "__main__":
    main()
