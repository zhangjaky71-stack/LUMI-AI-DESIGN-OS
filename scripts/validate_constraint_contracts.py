from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/constraints/v1"
SOURCE = ROOT / "services/constraint-engine/src/lumi_constraints"

EXPECTED_SCHEMA_IDS = {
    "constraint.schema.json": "https://schemas.lumi.dev/constraints/v1/constraint.schema.json",
    "violation.schema.json": "https://schemas.lumi.dev/constraints/v1/violation.schema.json",
    "override.schema.json": "https://schemas.lumi.dev/constraints/v1/override.schema.json",
    "evidence.schema.json": "https://schemas.lumi.dev/constraints/v1/evidence.schema.json",
}
EXPECTED_SOURCES = [
    "SAFETY_SYSTEM",
    "USER_EXPLICIT",
    "APPROVED_BRAND_RULE",
    "PROJECT_RULE",
    "RECIPE_RULE",
    "AGENT_INFERRED",
    "STYLE_PREFERENCE",
]
EXPECTED_SEVERITIES = ["HARD", "SOFT", "ADVISORY"]
FORBIDDEN_IMPORT_PREFIXES = (
    "fastapi",
    "sqlalchemy",
    "alembic",
    "langchain",
    "langgraph",
    "openai",
    "anthropic",
    "boto3",
    "httpx",
    "requests",
    "celery",
    "pika",
)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


def validate_contract_json() -> None:
    manifest = load(CONTRACT / "manifest.json")
    registry = load(CONTRACT / "evaluator-registry.json")

    types = manifest.get("constraint_types")
    assert isinstance(types, list) and len(types) == 24, "V1 must freeze exactly 24 constraint types"
    assert len(types) == len(set(types)), "duplicate constraint type"
    assert manifest.get("sources") == EXPECTED_SOURCES
    assert manifest.get("severities") == EXPECTED_SEVERITIES
    assert manifest.get("preflight_decisions") == ["ALLOW", "ALLOW_WITH_WARNINGS", "DENY"]
    assert manifest.get("postflight_outcomes") == ["PASS", "FAIL_REPAIRABLE", "FAIL_HARD"]

    precedence = manifest.get("source_precedence")
    assert isinstance(precedence, dict)
    values = [precedence[source] for source in EXPECTED_SOURCES]
    assert all(isinstance(value, int) for value in values)
    assert all(left > right for left, right in zip(values, values[1:], strict=True)), (
        "source precedence must strictly descend in frozen source order"
    )

    evaluators = registry.get("evaluators")
    assert isinstance(evaluators, dict)
    assert set(evaluators) == set(types), "every V1 constraint type must own one evaluator contract"
    for constraint_type, spec in evaluators.items():
        assert isinstance(spec, dict), constraint_type
        assert spec.get("phase") in {"PREFLIGHT", "POSTFLIGHT", "BOTH"}, constraint_type
        assert isinstance(spec.get("evaluator"), str) and spec["evaluator"], constraint_type
        if spec["phase"] in {"POSTFLIGHT", "BOTH"}:
            assert isinstance(spec.get("evidence"), str) and spec["evidence"], constraint_type

    for filename, expected_id in EXPECTED_SCHEMA_IDS.items():
        schema = load(CONTRACT / filename)
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", filename
        assert schema.get("$id") == expected_id, filename

    constraint_schema = load(CONTRACT / "constraint.schema.json")
    assert constraint_schema["properties"]["type"]["enum"] == types
    assert constraint_schema["properties"]["severity"]["enum"] == EXPECTED_SEVERITIES
    assert constraint_schema["properties"]["source"]["enum"] == EXPECTED_SOURCES

    violation_schema = load(CONTRACT / "violation.schema.json")
    message_pattern = violation_schema["properties"]["message_code"]["pattern"]
    assert message_pattern == "^CONSTRAINT_[A-Z0-9_]+$"
    assert "message" not in violation_schema["properties"], (
        "Violation contract must expose stable message_code, not localized UI prose"
    )

    evidence_schema = load(CONTRACT / "evidence.schema.json")
    evidence_kinds = set(evidence_schema["properties"]["kind"]["enum"])
    registered_evidence = {
        spec["evidence"]
        for spec in evaluators.values()
        if isinstance(spec, dict) and isinstance(spec.get("evidence"), str)
    }
    assert registered_evidence.issubset(evidence_kinds)


def validate_reference_boundary() -> None:
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                if name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    raise AssertionError(f"forbidden runtime dependency {name} in {path.relative_to(ROOT)}")
                if name.startswith("lumi_") and not (
                    name.startswith("lumi_constraints") or name.startswith("lumi_design_ir")
                ):
                    raise AssertionError(
                        f"constraint contract may depend only on Design IR among LUMI packages: {name}"
                    )


def main() -> None:
    validate_contract_json()
    validate_reference_boundary()
    print("Constraint V1 contracts OK: 24 types, evaluator registry, schemas and boundary validated")


if __name__ == "__main__":
    main()
