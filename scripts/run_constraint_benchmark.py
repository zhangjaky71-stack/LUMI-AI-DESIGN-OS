from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/design-ir/src"))
sys.path.insert(0, str(ROOT / "services/constraint-engine/src"))

from lumi_constraints import Constraint, ConstraintScope, PostflightEvidence, postflight, preflight  # noqa: E402

MATRIX = ROOT / "benchmarks/constraint-engine/v1/matrix.json"
CORPUS = ROOT / "contracts/design-ir/v1/fixtures/corpus.json"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected object: {path}")
    return value


def fixture(corpus: dict[str, Any], name: str) -> dict[str, Any]:
    for case in corpus["cases"]:
        if case["name"] == name:
            return deepcopy(case["document"])
    raise AssertionError(f"fixture not found: {name}")


def rule(
    constraint_id: str,
    constraint_type: str,
    node_id: str,
    *,
    severity: str = "HARD",
    parameters: dict[str, Any] | None = None,
    region: dict[str, Any] | None = None,
) -> Constraint:
    return Constraint(
        id=constraint_id,
        type=constraint_type,
        scope=ConstraintScope(node_ids=(node_id,), region=region),
        severity=severity,  # type: ignore[arg-type]
        source="USER_EXPLICIT",
        priority=1000,
        parameters=parameters or {},
    )


def execute_preflight(
    key: str,
    variant: int,
    document: dict[str, Any],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    n = variant + 1
    constraints: tuple[Constraint, ...]
    operation: dict[str, Any]

    if key == "only-background":
        constraints = (
            rule(f"logo-transform-{n}", "LOCK_TRANSFORM", "logo"),
            rule(f"logo-content-{n}", "LOCK_CONTENT", "logo"),
            rule(f"qr-transform-{n}", "LOCK_TRANSFORM", "qr"),
            rule(f"qr-content-{n}", "LOCK_CONTENT", "qr"),
        )
        operation = {
            "operation_id": f"op-background-{n}",
            "type": "SET_PROPERTY",
            "target_ids": ["frame"],
            "expected_document_version": 1,
            "payload": {"path": "frame.background.color", "value": "#000000" if variant % 2 == 0 else "#101010"},
            "reason": "only change background",
        }
    elif key == "keep-product":
        constraints = (
            rule(f"product-transform-{n}", "LOCK_TRANSFORM", "image"),
            rule(f"product-identity-{n}", "LOCK_IDENTITY", "image"),
        )
        operation = {
            "operation_id": f"op-product-move-{n}",
            "type": "MOVE_NODE",
            "target_ids": ["image"],
            "expected_document_version": 1,
            "payload": {"x": 10 + n, "y": 5 + n},
            "reason": "attempt to move protected product",
        }
    elif key == "resize-logo-proportionally":
        constraints = (rule(f"logo-ratio-{n}", "LOCK_ASPECT_RATIO", "logo"),)
        scale = 1 + n / 10
        operation = {
            "operation_id": f"op-logo-scale-{n}",
            "type": "RESIZE_NODE",
            "target_ids": ["logo"],
            "expected_document_version": 1,
            "payload": {"width": 160 * scale, "height": 80 * scale},
            "reason": "resize without distorting logo",
        }
    elif key == "keep-logo":
        constraints = (rule(f"logo-ratio-bad-{n}", "LOCK_ASPECT_RATIO", "logo"),)
        operation = {
            "operation_id": f"op-logo-distort-{n}",
            "type": "RESIZE_NODE",
            "target_ids": ["logo"],
            "expected_document_version": 1,
            "payload": {"width": 160 + n * 5, "height": 80 + n},
            "reason": "attempt distorted logo resize",
        }
    elif key == "keep-qr":
        constraints = (rule(f"qr-lock-{n}", "LOCK_TRANSFORM", "qr"),)
        operation = {
            "operation_id": f"op-qr-move-{n}",
            "type": "MOVE_NODE",
            "target_ids": ["qr"],
            "expected_document_version": 1,
            "payload": {"x": 520 - n, "y": 1320 - n},
            "reason": "attempt to move QR",
        }
    elif key == "change-title-size":
        constraints = ()
        operation = {
            "operation_id": f"op-title-resize-{n}",
            "type": "RESIZE_NODE",
            "target_ids": ["headline"],
            "expected_document_version": 1,
            "payload": {"width": 630, "height": 120 + n * 2},
            "reason": "change title size",
        }
    elif key == "safe-area":
        constraints = (
            rule(
                f"safe-area-{n}",
                "SAFE_AREA",
                "headline",
                region={"x": 0.05, "y": 0.05, "width": 0.9, "height": 0.9, "normalized": True},
            ),
        )
        operation = {
            "operation_id": f"op-outside-safe-area-{n}",
            "type": "MOVE_NODE",
            "target_ids": ["headline"],
            "expected_document_version": 1,
            "payload": {"x": 100 + n, "y": 80},
            "reason": "move outside safe area",
        }
    elif key == "non-overlap":
        constraints = (
            rule(
                f"non-overlap-{n}",
                "MUST_NOT_OVERLAP",
                "logo",
                parameters={"other_node_ids": ["qr"]},
            ),
        )
        operation = {
            "operation_id": f"op-overlap-{n}",
            "type": "MOVE_NODE",
            "target_ids": ["logo"],
            "expected_document_version": 1,
            "payload": {"x": 520 + variant % 3, "y": 1320 + variant % 3},
            "reason": "move logo over QR",
        }
    elif key == "soft-style-warning":
        constraints = (rule(f"soft-style-{n}", "LOCK_STYLE", "headline", severity="SOFT"),)
        operation = {
            "operation_id": f"op-font-size-{n}",
            "type": "SET_PROPERTY",
            "target_ids": ["headline"],
            "expected_document_version": 1,
            "payload": {"path": "text.font_size", "value": 72 + n},
            "reason": "style experiment",
        }
    else:
        raise AssertionError(f"unsupported preflight template: {key}")

    result = preflight(document, operation, constraints, current_document_version=1)
    return (
        result.decision,
        tuple(item.message_code for item in result.violations),
        tuple(item.message_code for item in result.warnings),
    )


def execute_postflight(key: str, variant: int) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    if key != "qr-postflight":
        raise AssertionError(f"unsupported postflight template: {key}")
    n = variant + 1
    constraint_id = f"qr-scan-{n}"
    constraint = rule(
        constraint_id,
        "REQUIRE_SCANNABILITY",
        "qr",
        parameters={"expected_payload_hash": f"payload-{n}"},
    )
    if variant % 2 == 0:
        evidence = PostflightEvidence(
            constraint_id=constraint_id,
            kind="qr",
            passed=True,
            actual={
                "detected": True,
                "decoded": True,
                "payload_match": True,
                "quiet_zone_ok": variant % 4 == 0,
                "size_ok": True,
            },
            repairable=True,
        )
    else:
        evidence = PostflightEvidence(
            constraint_id=constraint_id,
            kind="qr",
            passed=False,
            actual={
                "detected": True,
                "decoded": True,
                "payload_match": False,
                "quiet_zone_ok": True,
                "size_ok": True,
            },
            repairable=True,
        )
    result = postflight((constraint,), {constraint_id: evidence})
    return (
        result.outcome,
        tuple(item.message_code for item in result.violations),
        tuple(item.message_code for item in result.warnings),
    )


def expected_for(key: str, variant: int) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    if key == "only-background":
        return "ALLOW", (), ()
    if key == "keep-product":
        return "DENY", ("CONSTRAINT_POSITION_CHANGED",), ()
    if key == "resize-logo-proportionally":
        return "ALLOW", (), ()
    if key == "keep-logo":
        return "DENY", ("CONSTRAINT_ASPECT_RATIO_CHANGED",), ()
    if key == "keep-qr":
        return "DENY", ("CONSTRAINT_POSITION_CHANGED",), ()
    if key == "change-title-size":
        return "ALLOW", (), ()
    if key == "safe-area":
        return "DENY", ("CONSTRAINT_OUTSIDE_ALLOWED_REGION",), ()
    if key == "non-overlap":
        return "DENY", ("CONSTRAINT_OVERLAP_DETECTED",), ()
    if key == "soft-style-warning":
        return "ALLOW_WITH_WARNINGS", (), ("CONSTRAINT_STYLE_CHANGED",)
    if key == "qr-postflight":
        if variant % 2 == 1:
            return "FAIL_REPAIRABLE", ("CONSTRAINT_QR_NOT_SCANNABLE",), ()
        warning = () if variant % 4 == 0 else ("CONSTRAINT_QR_QUIET_ZONE_WARNING",)
        return "PASS", (), warning
    raise AssertionError(key)


def main() -> None:
    matrix = load_json(MATRIX)
    corpus = load_json(CORPUS)
    templates = matrix.get("templates")
    variants = matrix.get("variants_per_template")
    expected_count = matrix.get("expected_case_count")
    assert isinstance(templates, list) and len(templates) == 10
    assert variants == 10
    assert expected_count == 100

    seen: set[str] = set()
    failures: list[str] = []
    counts: dict[str, int] = {}
    for template in templates:
        assert isinstance(template, dict)
        key = template["key"]
        fixture_name = template["fixture"]
        mode = template["mode"]
        assert isinstance(key, str) and isinstance(fixture_name, str)
        counts[key] = 0
        for variant in range(variants):
            case_id = f"{key}-{variant + 1:02d}"
            assert case_id not in seen
            seen.add(case_id)
            counts[key] += 1
            expected = expected_for(key, variant)
            if mode == "preflight":
                actual = execute_preflight(key, variant, fixture(corpus, fixture_name))
            elif mode == "postflight":
                actual = execute_postflight(key, variant)
            else:
                raise AssertionError(f"unsupported mode: {mode}")
            if actual != expected:
                failures.append(f"{case_id}: expected={expected!r} actual={actual!r}")

    assert len(seen) == expected_count == 100
    assert all(count == 10 for count in counts.values())
    if failures:
        raise AssertionError("constraint benchmark failures:\n" + "\n".join(failures))
    print(f"Constraint benchmark PASS: {len(seen)} cases across {len(counts)} templates")


if __name__ == "__main__":
    main()
