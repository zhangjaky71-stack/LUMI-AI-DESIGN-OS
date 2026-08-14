from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/domain/src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_constraint_benchmark_corpus import build_corpus, validate_corpus  # noqa: E402
from lumi_domain.constraint_validator import guarded_execute  # noqa: E402

CONSTRAINT_SCHEMA = ROOT / "schemas/design-constraints/constraint.schema.json"
VIOLATION_SCHEMA = ROOT / "schemas/design-constraints/violation.schema.json"
SPEC_PATH = ROOT / "fixtures/constraints/node-39-benchmark-spec.json"
QR_FIXTURE = ROOT / "fixtures/constraints/qr-valid.png.base64"

EXPECTED_TYPES = {
    "LOCK_POSITION",
    "LOCK_SIZE",
    "LOCK_ROTATION",
    "LOCK_TRANSFORM",
    "LOCK_ASPECT_RATIO",
    "LOCK_LAYER_ORDER",
    "LOCK_PARENT",
    "LOCK_CONTENT",
    "LOCK_TEXT",
    "LOCK_ASSET",
    "LOCK_IDENTITY",
    "LOCK_STYLE",
    "LOCK_BRAND",
    "PROTECT_REGION",
    "MUST_STAY_INSIDE",
    "MUST_NOT_OVERLAP",
    "MIN_MARGIN",
    "SAFE_AREA",
    "REQUIRE_CONTRAST",
    "REQUIRE_SCANNABILITY",
    "REQUIRE_TEXT_READABILITY",
    "REQUIRE_BRAND_COMPLIANCE",
    "REQUIRE_RESOLUTION",
    "REQUIRE_IDENTITY_SCORE",
}


def _document() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "document_id": "validator-doc",
        "unit": "px",
        "root_id": "root",
        "nodes": {
            "root": {
                "id": "root",
                "kind": "DOCUMENT_ROOT",
                "parent_id": None,
                "children": ["qr"],
            },
            "qr": {
                "id": "qr",
                "kind": "IMAGE",
                "parent_id": "root",
                "children": [],
                "transform": {"x": 10, "y": 10, "width": 100, "height": 100},
            },
        },
        "resources": {},
        "metadata": {"document_version": 2},
    }


def validate_schema_contracts() -> None:
    constraint_schema = json.loads(CONSTRAINT_SCHEMA.read_text())
    violation_schema = json.loads(VIOLATION_SCHEMA.read_text())
    actual_types = set(constraint_schema["properties"]["type"]["enum"])
    if actual_types != EXPECTED_TYPES:
        missing = sorted(EXPECTED_TYPES - actual_types)
        extra = sorted(actual_types - EXPECTED_TYPES)
        raise SystemExit(f"constraint type drift: missing={missing} extra={extra}")
    required_violation_fields = {
        "constraint_id",
        "type",
        "severity",
        "validator",
        "reason_code",
    }
    if set(violation_schema["required"]) != required_violation_fields:
        raise SystemExit("violation schema required fields drifted")


def validate_fail_closed_preflight() -> None:
    operation = {
        "operation_id": "move-qr",
        "type": "MOVE_NODE",
        "target_ids": ["qr"],
        "expected_document_version": 2,
        "payload": {"dx": 5, "dy": 0},
    }
    constraint = {
        "id": "lock-qr",
        "type": "LOCK_POSITION",
        "scope": {"node_ids": ["qr"]},
        "severity": "HARD",
        "source": "USER_EXPLICIT",
        "priority": 1000,
        "parameters": {},
        "active": True,
        "document_version": 2,
    }
    result = guarded_execute(_document(), [operation], [constraint])
    if result["preflight"]["decision"] != "DENY" or "execution" in result:
        raise SystemExit("hard lock did not fail closed")


def validate_benchmark_spec() -> None:
    spec = json.loads(SPEC_PATH.read_text())
    rows = build_corpus(spec)
    validate_corpus(spec, rows)
    if len(rows) < 250:
        raise SystemExit("benchmark corpus must contain at least 250 cases")


def validate_fixture() -> None:
    import base64
    import hashlib

    payload = base64.b64decode(QR_FIXTURE.read_text().strip(), validate=True)
    digest = hashlib.sha256(payload).hexdigest()
    expected = "7f5abea4e4a9b2e542cec520122ce5caf160128db132f74bd6ac7a6b7afde091"
    if digest != expected:
        raise SystemExit(f"QR fixture hash drift: {digest}")


def main() -> None:
    validate_schema_contracts()
    validate_fail_closed_preflight()
    validate_benchmark_spec()
    validate_fixture()
    print("NODE-39 constraint runtime contract: OK")


if __name__ == "__main__":
    main()
