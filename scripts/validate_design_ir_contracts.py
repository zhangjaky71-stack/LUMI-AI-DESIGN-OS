from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/design-ir/v1"
SERVICE_SRC = ROOT / "services/design-ir/src"
sys.path.insert(0, str(SERVICE_SRC))

from lumi_design_ir import DesignIRError, validate_document  # noqa: E402


EXPECTED_SCHEMA_ID = "https://schemas.lumi.dev/design-ir/v1/design-document.schema.json"
EXPECTED_OPERATION_SCHEMA_ID = "https://schemas.lumi.dev/design-ir/v1/operation.schema.json"
FORBIDDEN_PERSISTED_TERMS = ("pixi", "react", "presigned_url", "dom_element_id", "texture_id")


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected object in {path}")
    return value


def main() -> None:
    manifest = _load(CONTRACT / "type-manifest.json")
    document_schema = _load(CONTRACT / "design-document.schema.json")
    operation_schema = _load(CONTRACT / "operation.schema.json")
    corpus = _load(CONTRACT / "fixtures/corpus.json")

    assert document_schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert operation_schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert document_schema.get("$id") == EXPECTED_SCHEMA_ID
    assert operation_schema.get("$id") == EXPECTED_OPERATION_SCHEMA_ID
    assert manifest.get("schema_version") == "1.0"
    assert manifest.get("range_indexing") == "UNICODE_CODE_POINT"
    assert manifest.get("canonicalization") == "LUMI_CANONICAL_JSON_V1"

    node_enum = document_schema["$defs"]["node"]["properties"]["kind"]["enum"]  # type: ignore[index]
    assert node_enum == manifest["node_kinds"]

    operation_constants: set[str] = set()
    for variant in operation_schema.get("oneOf", []):
        ref = variant.get("$ref")
        assert isinstance(ref, str) and ref.startswith("#/$defs/")
        name = ref.rsplit("/", 1)[-1]
        definition = operation_schema["$defs"][name]  # type: ignore[index]
        op_type = definition["allOf"][1]["properties"]["type"]["const"]  # type: ignore[index]
        operation_constants.add(op_type)
    assert operation_constants == set(manifest["operation_types"])

    schema_text = (CONTRACT / "design-document.schema.json").read_text(encoding="utf-8").lower()
    for forbidden in FORBIDDEN_PERSISTED_TERMS:
        assert forbidden not in schema_text, f"renderer/UI ephemeral term leaked into IR schema: {forbidden}"

    cases = corpus.get("cases")
    assert isinstance(cases, list) and len(cases) >= 10
    valid = invalid = 0
    names: set[str] = set()
    for case in cases:
        assert isinstance(case, dict)
        name = case.get("name")
        expect = case.get("expect")
        document = case.get("document")
        assert isinstance(name, str) and name not in names
        assert isinstance(document, dict)
        names.add(name)
        if expect == "valid":
            validate_document(document)
            valid += 1
        elif expect == "invalid":
            try:
                validate_document(document)
            except DesignIRError as exc:
                expected_error = case.get("error")
                if expected_error is not None:
                    assert type(exc).__name__ == expected_error, (name, type(exc).__name__, expected_error)
            else:
                raise AssertionError(f"invalid fixture unexpectedly passed: {name}")
            invalid += 1
        else:
            raise AssertionError(f"unknown fixture expectation for {name}: {expect}")

    assert valid >= 8
    assert invalid >= 2
    print(
        f"Design IR contracts OK: {len(cases)} fixtures ({valid} valid/{invalid} invalid), "
        f"{len(manifest['node_kinds'])} node kinds, {len(manifest['operation_types'])} operations"
    )


if __name__ == "__main__":
    main()
