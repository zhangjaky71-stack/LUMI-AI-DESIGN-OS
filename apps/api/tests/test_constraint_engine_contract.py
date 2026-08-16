from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from lumi_api.constraints import (
    EVALUATOR_CONTRACTS,
    Constraint,
    ConstraintDenied,
    ConstraintOverride,
    ConstraintScope,
    ConstraintSet,
    ExplicitTarget,
    PostflightObservation,
    apply_batch_with_constraints,
    constraint_snapshot_hash,
    evaluate_postflight,
    evaluate_preflight,
    resolve_active_constraints,
    structure_explicit_user_locks,
)
from lumi_api.design_ir.document import DesignIRDocument
from lumi_api.design_ir.nodes import ImageNode, PageNode, TextNode
from lumi_api.design_ir.operations import (
    ActorRef,
    DesignOperation,
    DesignOperationBatch,
    SetSizeOp,
    SetTextOp,
    SetTransformOp,
)
from lumi_api.design_ir.primitives import RgbaColor, Size2D, TextStyle, Transform2D
from lumi_api.domain.ids import new_uuid7


def fixture_document() -> tuple[DesignIRDocument, UUID, UUID, UUID]:
    page = new_uuid7()
    qr = new_uuid7()
    product = new_uuid7()
    text = new_uuid7()
    nodes = (
        PageNode(
            id=page,
            name="Page",
            size=Size2D(width=750, height=1624),
            children=(qr, product, text),
        ),
        ImageNode(
            id=qr,
            name="二维码",
            parent_id=page,
            size=Size2D(width=180, height=180),
            asset_id=new_uuid7(),
            semantic_tags=("qr",),
        ),
        ImageNode(
            id=product,
            name="产品",
            parent_id=page,
            size=Size2D(width=320, height=240),
            asset_id=new_uuid7(),
            semantic_tags=("product",),
        ),
        TextNode(
            id=text,
            name="标题",
            parent_id=page,
            size=Size2D(width=400, height=80),
            text="HELLO",
            style=TextStyle(
                font_family="Inter",
                font_size=48,
                color=RgbaColor(r=0, g=0, b=0, a=1),
            ),
        ),
    )
    document = DesignIRDocument(
        document_id=new_uuid7(),
        revision=1,
        pages=(page,),
        nodes=nodes,
    )
    return document, qr, product, text


def batch(document: DesignIRDocument, *ops: DesignOperation) -> DesignOperationBatch:
    return DesignOperationBatch(
        operation_id=new_uuid7(),
        document_id=document.document_id,
        base_revision=document.revision,
        actor=ActorRef(kind="user", actor_id="u1"),
        operations=ops,
    )


def test_hard_position_lock_denies_transform() -> None:
    document, qr, _, _ = fixture_document()
    constraint = Constraint(
        id=new_uuid7(),
        type="LOCK_POSITION",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="USER_EXPLICIT",
        priority=1_000,
    )
    result = evaluate_preflight(
        document,
        batch(document, SetTransformOp(node_id=qr, transform=Transform2D(x=10, y=20))),
        ConstraintSet(constraints=(constraint,)),
    )
    assert result.decision == "DENY"
    assert result.violations[0].message_code == "CONSTRAINT_LOCK_POSITION_VIOLATION"


def test_soft_lock_warns_but_allows() -> None:
    document, qr, _, _ = fixture_document()
    constraint = Constraint(
        id=new_uuid7(),
        type="LOCK_POSITION",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="SOFT",
        source="PROJECT_RULE",
    )
    result = evaluate_preflight(
        document,
        batch(document, SetTransformOp(node_id=qr, transform=Transform2D(x=1))),
        ConstraintSet(constraints=(constraint,)),
    )
    assert result.decision == "ALLOW_WITH_WARNINGS"
    assert not result.violations


def test_precedence_prefers_user_explicit_over_agent_inferred() -> None:
    _, qr, _, _ = fixture_document()
    agent = Constraint(
        id=new_uuid7(),
        type="LOCK_SIZE",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="ADVISORY",
        source="AGENT_INFERRED",
        parameters={"expected": "agent"},
    )
    user = Constraint(
        id=new_uuid7(),
        type="LOCK_SIZE",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="USER_EXPLICIT",
        parameters={"expected": "user"},
    )
    resolved, conflicts = resolve_active_constraints(ConstraintSet(constraints=(agent, user)))
    assert resolved == (user,)
    assert not conflicts


def test_same_level_conflict_is_not_silently_resolved() -> None:
    _, qr, _, _ = fixture_document()
    first = Constraint(
        id=new_uuid7(),
        type="LOCK_SIZE",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="USER_EXPLICIT",
        priority=100,
        parameters={"expected": "a"},
    )
    second = Constraint(
        id=new_uuid7(),
        type="LOCK_SIZE",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="USER_EXPLICIT",
        priority=100,
        parameters={"expected": "b"},
    )
    resolved, conflicts = resolve_active_constraints(
        ConstraintSet(constraints=(first, second))
    )
    assert not resolved
    assert len(conflicts) == 1


def test_constrained_apply_preserves_atomicity_on_denial() -> None:
    document, qr, _, _ = fixture_document()
    constraint = Constraint(
        id=new_uuid7(),
        type="LOCK_POSITION",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="USER_EXPLICIT",
    )
    operation_batch = batch(
        document,
        SetTransformOp(node_id=qr, transform=Transform2D(x=50)),
        SetSizeOp(node_id=qr, size=Size2D(width=200, height=200)),
    )
    with pytest.raises(ConstraintDenied):
        apply_batch_with_constraints(
            document,
            operation_batch,
            ConstraintSet(constraints=(constraint,)),
        )
    assert document.revision == 1
    node = next(item for item in document.nodes if item.id == qr)
    assert node.transform.x == 0


def test_override_allows_non_safety_constraint() -> None:
    document, qr, _, _ = fixture_document()
    constraint = Constraint(
        id=new_uuid7(),
        type="LOCK_POSITION",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="USER_EXPLICIT",
    )
    override = ConstraintOverride(
        override_id=new_uuid7(),
        constraint_id=constraint.id,
        actor_id="owner",
        reason="approved campaign correction",
        occurred_at=datetime.now(UTC),
        policy_decision_id="policy-1",
    )
    result = evaluate_preflight(
        document,
        batch(document, SetTransformOp(node_id=qr, transform=Transform2D(x=10))),
        ConstraintSet(constraints=(constraint,)),
        overrides=(override,),
    )
    assert result.decision == "ALLOW"
    assert result.applied_override_ids == (override.override_id,)


def test_safety_constraint_cannot_be_overridden() -> None:
    document, qr, _, _ = fixture_document()
    constraint = Constraint(
        id=new_uuid7(),
        type="LOCK_POSITION",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="SAFETY_SYSTEM",
    )
    override = ConstraintOverride(
        override_id=new_uuid7(),
        constraint_id=constraint.id,
        actor_id="owner",
        reason="attempt override safety",
        occurred_at=datetime.now(UTC),
        policy_decision_id="policy-2",
    )
    result = evaluate_preflight(
        document,
        batch(document, SetTransformOp(node_id=qr, transform=Transform2D(x=10))),
        ConstraintSet(constraints=(constraint,)),
        overrides=(override,),
    )
    assert result.decision == "DENY"
    assert not result.applied_override_ids


def test_stale_revision_and_missing_target_fail_closed() -> None:
    document, _, _, _ = fixture_document()
    bad_batch = DesignOperationBatch(
        operation_id=new_uuid7(),
        document_id=document.document_id,
        base_revision=99,
        actor=ActorRef(kind="user", actor_id="u1"),
        operations=(SetTextOp(node_id=new_uuid7(), text="x"),),
    )
    result = evaluate_preflight(document, bad_batch, ConstraintSet())
    codes = {item.message_code for item in result.violations}
    assert "CONSTRAINT_STALE_DOCUMENT_VERSION" in codes
    assert "CONSTRAINT_TARGET_MISSING" in codes


def test_qr_postflight_hard_failure_blocks_approval() -> None:
    _, qr, _, _ = fixture_document()
    constraint = Constraint(
        id=new_uuid7(),
        type="REQUIRE_SCANNABILITY",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="USER_EXPLICIT",
    )
    observation = PostflightObservation(
        kind="qr_scannability",
        target_id=qr,
        metrics={
            "detected": True,
            "decoded": False,
            "payload_match": False,
            "quiet_zone_ok": False,
        },
    )
    result = evaluate_postflight(
        ConstraintSet(constraints=(constraint,)),
        (observation,),
    )
    assert result.status == "FAIL_HARD"
    assert result.can_approve is False


def test_qr_quiet_zone_is_warning_when_core_scan_passes() -> None:
    _, qr, _, _ = fixture_document()
    constraint = Constraint(
        id=new_uuid7(),
        type="REQUIRE_SCANNABILITY",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="USER_EXPLICIT",
    )
    observation = PostflightObservation(
        kind="qr_scannability",
        target_id=qr,
        metrics={
            "detected": True,
            "decoded": True,
            "payload_match": True,
            "quiet_zone_ok": False,
            "module_size_ok": True,
        },
    )
    result = evaluate_postflight(
        ConstraintSet(constraints=(constraint,)),
        (observation,),
    )
    assert result.status == "FAIL_REPAIRABLE"
    assert result.can_approve is True
    assert result.warnings


def test_protected_region_diff_threshold() -> None:
    constraint = Constraint(
        id=new_uuid7(),
        type="PROTECT_REGION",
        severity="HARD",
        source="USER_EXPLICIT",
        parameters={"max_difference": 0.03},
    )
    passing = PostflightObservation(
        kind="protected_region",
        metrics={"difference_score": 0.02},
    )
    failing = PostflightObservation(
        kind="protected_region",
        metrics={"difference_score": 0.08},
    )
    constraint_set = ConstraintSet(constraints=(constraint,))
    assert evaluate_postflight(constraint_set, (passing,)).status == "PASS"
    assert evaluate_postflight(constraint_set, (failing,)).status == "FAIL_HARD"


def test_snapshot_hash_is_order_independent() -> None:
    _, qr, product, _ = fixture_document()
    first = Constraint(
        id=new_uuid7(),
        type="LOCK_POSITION",
        scope=ConstraintScope(node_ids=(qr,)),
        severity="HARD",
        source="USER_EXPLICIT",
    )
    second = Constraint(
        id=new_uuid7(),
        type="LOCK_IDENTITY",
        scope=ConstraintScope(node_ids=(product,)),
        severity="HARD",
        source="USER_EXPLICIT",
    )
    forward = constraint_snapshot_hash(ConstraintSet(constraints=(first, second)))
    reverse = constraint_snapshot_hash(ConstraintSet(constraints=(second, first)))
    assert forward == reverse


def test_explicit_language_structures_qr_and_product_locks() -> None:
    _, qr, product, _ = fixture_document()
    result = structure_explicit_user_locks(
        "二维码和产品都不要动，只把背景改黑色",
        (
            ExplicitTarget("二维码", qr, "qr"),
            ExplicitTarget("产品", product, "product"),
        ),
    )
    types = [item.type for item in result.constraints]
    assert types.count("LOCK_TRANSFORM") == 2
    assert "LOCK_CONTENT" in types
    assert "REQUIRE_SCANNABILITY" in types
    assert "LOCK_IDENTITY" in types
    assert all(
        item.source == "USER_EXPLICIT" and item.severity == "HARD"
        for item in result.constraints
    )


def test_explicit_language_does_not_lock_other_clause_targets() -> None:
    _, qr, product, _ = fixture_document()
    result = structure_explicit_user_locks(
        "二维码不要动，产品换成新图",
        (
            ExplicitTarget("二维码", qr, "qr"),
            ExplicitTarget("产品", product, "product"),
        ),
    )
    assert {item.scope.node_ids[0] for item in result.constraints} == {qr}


def test_all_v1_constraint_types_have_evaluator_contracts() -> None:
    assert len(EVALUATOR_CONTRACTS) == 24
    assert all(contract.stages for contract in EVALUATOR_CONTRACTS.values())
