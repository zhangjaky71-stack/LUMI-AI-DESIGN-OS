from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from lumi_domain.design_ir_runtime import canonical_sha256, execute_operations

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/design-ir/node-38-conformance.json"
TS_TYPES = ROOT / "packages/design-ir/src/types.ts"
TS_EXECUTOR = ROOT / "packages/design-ir/src/executor.ts"
PY_RUNTIME = ROOT / "services/domain/src/lumi_domain/design_ir_runtime.py"

FROZEN_OPERATIONS = {
    "CREATE_NODE",
    "DELETE_NODE",
    "SET_PROPERTY",
    "MOVE_NODE",
    "RESIZE_NODE",
    "ROTATE_NODE",
    "REORDER_NODE",
    "REPARENT_NODE",
    "REPLACE_ASSET",
    "SET_TEXT",
    "APPLY_STYLE",
    "BATCH",
}


def main() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ts_types = TS_TYPES.read_text(encoding="utf-8")
    ts_executor = TS_EXECUTOR.read_text(encoding="utf-8")
    py_runtime = PY_RUNTIME.read_text(encoding="utf-8")

    for operation in sorted(FROZEN_OPERATIONS):
        assert f'"{operation}"' in ts_types, f"TypeScript contract missing {operation}"
        assert f'"{operation}"' in ts_executor, f"TypeScript executor missing {operation}"
        assert f'"{operation}"' in py_runtime, f"Python runtime missing {operation}"

    document = fixture["document"]
    assert canonical_sha256(document) == fixture["expected_input_sha256"]
    result = execute_operations(document, fixture["operations"])
    assert result["ok"] is True
    assert canonical_sha256(result["document"]) == fixture["expected_output_sha256"]

    failing = deepcopy(fixture["operations"])
    failing.append(
        {
            "operation_id": "validator-missing-target",
            "type": "SET_TEXT",
            "target_ids": ["missing"],
            "expected_document_version": document["metadata"]["document_version"],
            "payload": {"content": "rollback"},
        }
    )
    failure = execute_operations(document, failing)
    assert failure["ok"] is False
    assert failure["document"] is document, "Atomic failure must return the exact input document"
    assert document["nodes"]["headline"]["content"] == "Hello", "Input document was mutated"

    print("NODE-38 Design IR Runtime contract: PASS")


if __name__ == "__main__":
    main()
