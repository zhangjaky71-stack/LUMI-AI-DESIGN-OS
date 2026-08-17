from __future__ import annotations

import copy
import random

from lumi_api.constraint_validator import (
    P0_VALIDATORS,
    RuntimeConstraint,
    RuntimeScope,
    ValidationAdapters,
    ValidationPolicy,
    validate_batch,
    validate_constraints,
    validate_export,
)
from lumi_api.constraint_validator.solver import (
    propose_fix_operations,
    validate_proposed_fix,
    validate_proposed_fix_with_ir_runtime,
)


def document() -> dict:
    return {
        "schema_version": "1.0",
        "document_id": "poster",
        "unit": "px",
        "root_id": "root",
        "nodes": {
            "root": {
                "id": "root",
                "kind": "DOCUMENT_ROOT",
                "parent_id": None,
                "children": ["frame"],
                "transform": {"x": 0, "y": 0, "width": 750, "height": 1624},
            },
            "frame": {
                "id": "frame",
                "kind": "FRAME",
                "parent_id": "root",
                "children": ["headline", "qr", "logo", "hero"],
                "transform": {"x": 0, "y": 0, "width": 750, "height": 1624},
            },
            "headline": {
                "id": "headline",
                "kind": "TEXT",
                "role": "HEADLINE",
                "parent_id": "frame",
                "children": [],
                "content": "夏日咖啡",
                "font_size": 48,
                "font_family": "Inter",
                "fill": "#111111",
                "background": "#ffffff",
                "transform": {"x": 80, "y": 100, "width": 500, "height": 100},
            },
            "qr": {
                "id": "qr",
                "kind": "IMAGE",
                "role": "QR_CODE",
                "parent_id": "frame",
                "children": [],
                "quiet_zone_px": 12,
                "foreground": "#000000",
                "background": "#ffffff",
                "transform": {"x": 550, "y": 1400, "width": 120, "height": 120},
            },
            "logo": {
                "id": "logo",
                "kind": "IMAGE",
                "role": "LOGO",
                "parent_id": "frame",
                "children": [],
                "locked": True,
                "transform": {"x": 50, "y": 50, "width": 100, "height": 60, "rotation_deg": 0},
            },
            "hero": {
                "id": "hero",
                "kind": "IMAGE",
                "role": "HERO_PRODUCT",
                "parent_id": "frame",
                "children": [],
                "asset_id": "asset-a",
                "fill": "#ffcc00",
                "transform": {"x": 100, "y": 400, "width": 500, "height": 500},
            },
        },
        "resources": {},
        "metadata": {"document_version": 7},
    }


def c(cid: str, ctype: str, severity: str = "HARD", nodes: tuple[str, ...] = (), **params):
    return RuntimeConstraint(
        cid,
        ctype,
        severity,
        RuntimeScope(node_ids=nodes),
        params,
    )


def test_p0_validator_registry_is_complete():
    assert len(P0_VALIDATORS) == 12


def test_prospective_move_is_blocked_before_commit():
    rule = c(
        "bounds",
        "MUST_STAY_INSIDE",
        nodes=("headline",),
        region={"x": 0, "y": 0, "width": 750, "height": 1624},
    )
    operation = {
        "operation_id": "move-1",
        "type": "MOVE_NODE",
        "target_ids": ["headline"],
        "expected_document_version": 7,
        "payload": {"x": 700, "y": 100},
    }
    original = document()
    report = validate_constraints(original, (rule,), operation=operation)
    assert report.status == "BLOCKED"
    assert report.violations[0].validator == "BoundsValidator"
    assert original["nodes"]["headline"]["transform"]["x"] == 80


def test_locked_region_mutation_blocks_but_full_export_does_not_fail_for_lock_itself():
    rule = c("lock", "LOCK_TRANSFORM", nodes=("logo",))
    op = {
        "operation_id": "logo-move",
        "type": "MOVE_NODE",
        "target_ids": ["logo"],
        "expected_document_version": 7,
        "payload": {"x": 90, "y": 90},
    }
    assert validate_constraints(document(), (rule,), operation=op).hard_pass is False
    assert validate_export(document(), (rule,)).hard_pass is True


def test_cjk_overflow_requires_real_measurement_and_never_uses_latin_heuristic():
    rule = c("text", "REQUIRE_TEXT_READABILITY", nodes=("headline",), require_measurement=True)
    missing = validate_constraints(document(), (rule,))
    assert missing.status == "BLOCKED"
    assert any(item.unavailable for item in missing.violations)
    adapters = ValidationAdapters(
        text_measure=lambda node: {"width": 700, "height": 100, "lines": 1}
    )
    measured = validate_constraints(document(), (rule,), adapters=adapters)
    assert any(
        item.validator == "TextOverflowValidator" and not item.unavailable
        for item in measured.violations
    )


def test_qr_geometry_and_decode_are_enforced():
    rule = c("qr-rule", "REQUIRE_SCANNABILITY", nodes=("qr",), min_size_px=128, require_decode=True)
    report = validate_constraints(document(), (rule,))
    codes = {item.message for item in report.violations}
    assert report.hard_pass is False
    assert any("minimum" in message for message in codes)
    assert any(item.unavailable for item in report.violations)
    adapters = ValidationAdapters(qr_decode=lambda node: True)
    decoded = validate_constraints(document(), (rule,), adapters=adapters)
    assert not any(item.unavailable for item in decoded.violations)


def test_identity_missing_baseline_is_unavailable_not_pass():
    rule = c("identity", "REQUIRE_IDENTITY_SCORE", nodes=("hero",), min_score=0.95)
    report = validate_constraints(document(), (rule,))
    assert report.status == "BLOCKED"
    assert report.violations[0].unavailable is True
    adapters = ValidationAdapters(identity_score=lambda node: 0.80)
    measured = validate_constraints(document(), (rule,), adapters=adapters)
    assert measured.violations[0].measured_value == 0.80


def test_brand_tokens_and_logo_transform():
    rule = c(
        "brand",
        "REQUIRE_BRAND_COMPLIANCE",
        nodes=("headline", "logo"),
        allowed_fonts=["Brand Sans"],
        logo_rotation_forbidden=True,
    )
    report = validate_constraints(document(), (rule,))
    assert any(item.validator == "BrandTokenValidator" for item in report.violations)


def test_export_dimension_gate_forces_full_scan():
    rule = c("export", "REQUIRE_RESOLUTION", nodes=("frame",), width=750, height=1624)
    assert validate_export(document(), (rule,)).hard_pass is True
    bad = c("export", "REQUIRE_RESOLUTION", nodes=("frame",), width=1080, height=1920)
    report = validate_export(document(), (bad,))
    assert report.hard_pass is False
    assert report.metrics.fallback_full_scan is True


def test_stable_violation_ids_and_health_score_are_deterministic():
    rule = c(
        "font",
        "REQUIRE_TEXT_READABILITY",
        nodes=("headline",),
        min_font_size=60,
        require_measurement=False,
    )
    first = validate_constraints(document(), (rule,))
    second = validate_constraints(copy.deepcopy(document()), (rule,))
    assert first.violations[0].violation_id == second.violations[0].violation_id
    assert first.health_score == second.health_score == 0.0


def test_incremental_matches_full_for_impacted_fixture():
    rules = (
        c(
            "font",
            "REQUIRE_TEXT_READABILITY",
            nodes=("headline",),
            min_font_size=60,
            require_measurement=False,
        ),
    )
    op = {
        "operation_id": "font-op",
        "type": "SET_PROPERTY",
        "target_ids": ["headline"],
        "expected_document_version": 7,
        "payload": {"property": "font_size", "value": 30},
    }
    policy = ValidationPolicy(incremental_full_scan_ratio=1.0)
    incremental = validate_constraints(document(), rules, operation=op, policy=policy)
    candidate = copy.deepcopy(document())
    candidate["nodes"]["headline"]["font_size"] = 30
    full = validate_constraints(candidate, rules, force_full=True, policy=policy)
    assert incremental.metrics.fallback_full_scan is False
    assert {v.violation_id for v in incremental.violations} == {
        v.violation_id for v in full.violations
    }


def test_batch_returns_all_relevant_blocking_violations_and_is_side_effect_free():
    rules = (
        c(
            "bounds",
            "MUST_STAY_INSIDE",
            nodes=("headline",),
            region={"x": 0, "y": 0, "width": 750, "height": 1624},
        ),
        c("lock", "LOCK_TRANSFORM", nodes=("logo",)),
    )
    ops = (
        {
            "operation_id": "move-head",
            "type": "MOVE_NODE",
            "target_ids": ["headline"],
            "payload": {"x": 740, "y": 100},
        },
        {
            "operation_id": "move-logo",
            "type": "MOVE_NODE",
            "target_ids": ["logo"],
            "payload": {"x": 120, "y": 50},
        },
    )
    original = document()
    report = validate_batch(original, rules, ops)
    assert report.metrics.blocking_count == 2
    assert {item.constraint_id for item in report.violations} == {"bounds", "lock"}
    assert original == document()


def test_solver_never_autofixes_protected_or_brand_and_revalidates_safe_fix():
    rules = (
        c(
            "font",
            "REQUIRE_TEXT_READABILITY",
            nodes=("headline",),
            min_font_size=60,
            require_measurement=False,
        ),
        c("brand", "REQUIRE_BRAND_COMPLIANCE", nodes=("headline",), allowed_fonts=["Brand Sans"]),
    )
    report = validate_constraints(document(), rules)
    ops = propose_fix_operations(report.violations, document_version=7)
    assert len(ops) == 1
    assert ops[0]["payload"]["property"] == "font_size"
    revalidated = validate_proposed_fix(document(), rules, ops[0])
    assert not any(v.validator == "FontSizeValidator" for v in revalidated.violations)


def test_lock_facets_do_not_overblock_unrelated_operations():
    rule = c("text-lock", "LOCK_TEXT", nodes=("headline",))
    move = {
        "operation_id": "move",
        "type": "MOVE_NODE",
        "target_ids": ["headline"],
        "payload": {"x": 100, "y": 100},
    }
    edit = {
        "operation_id": "text",
        "type": "SET_TEXT",
        "target_ids": ["headline"],
        "payload": {"content": "new"},
    }
    assert validate_constraints(document(), (rule,), operation=move).hard_pass is True
    assert validate_constraints(document(), (rule,), operation=edit).hard_pass is False


def test_adapter_failure_is_unavailable_and_hard_fails_closed():
    rule = c("identity", "REQUIRE_IDENTITY_SCORE", nodes=("hero",))

    def broken(node):
        raise RuntimeError("provider unavailable")

    report = validate_constraints(
        document(),
        (rule,),
        adapters=ValidationAdapters(identity_score=broken),
    )
    assert report.status == "BLOCKED"
    assert report.violations[0].unavailable is True


def test_safe_fix_can_be_forced_through_ir_runtime_before_second_validation():
    rule = c(
        "font",
        "REQUIRE_TEXT_READABILITY",
        nodes=("headline",),
        min_font_size=60,
        require_measurement=False,
    )
    report = validate_constraints(document(), (rule,))
    operation = propose_fix_operations(report.violations, document_version=7)[0]
    calls = []

    def ir_apply(doc, op):
        calls.append(op["operation_id"])
        candidate = copy.deepcopy(doc)
        candidate["nodes"]["headline"]["font_size"] = op["payload"]["value"]
        return candidate

    checked = validate_proposed_fix_with_ir_runtime(
        document(),
        (rule,),
        operation,
        apply_ir_runtime=ir_apply,
    )
    assert calls == [operation["operation_id"]]
    assert not any(v.validator == "FontSizeValidator" for v in checked.violations)


def test_random_geometry_never_changes_stable_blocking_semantics():
    rng = random.Random(39)
    rule = c(
        "bounds",
        "MUST_STAY_INSIDE",
        nodes=("hero",),
        region={"x": 0, "y": 0, "width": 750, "height": 1624},
    )
    for index in range(100):
        x = rng.randint(-100, 800)
        y = rng.randint(-100, 1700)
        op = {
            "operation_id": f"move-{index}",
            "type": "MOVE_NODE",
            "target_ids": ["hero"],
            "payload": {"x": x, "y": y},
        }
        report = validate_constraints(document(), (rule,), operation=op)
        expected_block = x < 0 or y < 0 or x + 500 > 750 or y + 500 > 1624
        assert (not report.hard_pass) is expected_block
