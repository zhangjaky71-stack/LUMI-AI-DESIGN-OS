from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/design-ir/src"))
sys.path.insert(0, str(ROOT / "services/constraint-engine/src"))

from lumi_constraints import (  # noqa: E402
    Constraint,
    ConstraintScope,
    OverrideDenied,
    PostflightEvidence,
    compile_user_explicit_protections,
    constraint_snapshot_hash,
    create_override_audit,
    detect_conflicts,
    effective_constraints,
    postflight,
    preflight,
)

CORPUS = json.loads(
    (ROOT / "contracts/design-ir/v1/fixtures/corpus.json").read_text(encoding="utf-8")
)


def fixture(name: str) -> dict:
    for case in CORPUS["cases"]:
        if case["name"] == name:
            return deepcopy(case["document"])
    raise KeyError(name)


def constraint(
    constraint_id: str,
    constraint_type: str,
    node_id: str,
    *,
    severity: str = "HARD",
    source: str = "USER_EXPLICIT",
    priority: int = 1000,
    parameters: dict | None = None,
) -> Constraint:
    return Constraint(
        id=constraint_id,
        type=constraint_type,
        scope=ConstraintScope(node_ids=(node_id,)),
        severity=severity,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        priority=priority,
        parameters=parameters or {},
    )


class ConstraintEngineTests(unittest.TestCase):
    def test_geometry_lock_denies_move(self) -> None:
        document = fixture("single-frame-poster")
        result = preflight(
            document,
            {
                "operation_id": "move-headline",
                "type": "MOVE_NODE",
                "target_ids": ["headline"],
                "expected_document_version": 4,
                "payload": {"x": 140, "y": 160},
                "reason": "move title",
            },
            (constraint("lock-pos", "LOCK_POSITION", "headline"),),
            current_document_version=4,
        )
        self.assertEqual(result.decision, "DENY")
        self.assertEqual(result.violations[0].message_code, "CONSTRAINT_POSITION_CHANGED")
        self.assertEqual(document["nodes"]["headline"]["transform"]["x"], 60)

    def test_aspect_ratio_allows_proportional_resize_and_denies_distortion(self) -> None:
        document = fixture("logo-and-qr-locks")
        ratio_lock = constraint("logo-ratio", "LOCK_ASPECT_RATIO", "logo")
        proportional = preflight(
            document,
            {
                "operation_id": "resize-logo-ok",
                "type": "RESIZE_NODE",
                "target_ids": ["logo"],
                "expected_document_version": 1,
                "payload": {"width": 320, "height": 160},
                "reason": "scale logo",
            },
            (ratio_lock,),
            current_document_version=1,
        )
        self.assertEqual(proportional.decision, "ALLOW")

        distorted = preflight(
            document,
            {
                "operation_id": "resize-logo-bad",
                "type": "RESIZE_NODE",
                "target_ids": ["logo"],
                "expected_document_version": 1,
                "payload": {"width": 320, "height": 100},
                "reason": "distort logo",
            },
            (ratio_lock,),
            current_document_version=1,
        )
        self.assertEqual(distorted.decision, "DENY")
        self.assertEqual(distorted.violations[0].message_code, "CONSTRAINT_ASPECT_RATIO_CHANGED")

    def test_user_explicit_precedence_beats_agent_inferred_same_rule(self) -> None:
        agent = constraint(
            "agent-margin",
            "MIN_MARGIN",
            "headline",
            source="AGENT_INFERRED",
            priority=1000,
            parameters={"margin": 8},
        )
        user = constraint(
            "user-margin",
            "MIN_MARGIN",
            "headline",
            source="USER_EXPLICIT",
            priority=10,
            parameters={"margin": 24},
        )
        selected = effective_constraints((agent, user))
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].id, "user-margin")

    def test_same_level_conflicting_hard_rules_are_explicit_conflict(self) -> None:
        first = constraint(
            "margin-a",
            "MIN_MARGIN",
            "headline",
            parameters={"margin": 10},
        )
        second = constraint(
            "margin-b",
            "MIN_MARGIN",
            "headline",
            parameters={"margin": 30},
        )
        conflicts = detect_conflicts((first, second))
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].phase, "CONFLICT")
        self.assertEqual(conflicts[0].message_code, "CONSTRAINT_PRECEDENCE_CONFLICT")

        result = preflight(
            fixture("single-frame-poster"),
            {
                "operation_id": "move-with-conflict",
                "type": "MOVE_NODE",
                "target_ids": ["headline"],
                "expected_document_version": 1,
                "payload": {"x": 70, "y": 90},
                "reason": "conflicting rules",
            },
            (first, second),
            current_document_version=1,
        )
        self.assertEqual(result.decision, "DENY")
        self.assertEqual(result.violations[0].phase, "CONFLICT")

    def test_batch_hard_violation_denies_whole_candidate(self) -> None:
        document = fixture("logo-and-qr-locks")
        before = deepcopy(document)
        qr_lock = constraint("qr-lock", "LOCK_TRANSFORM", "qr")
        operation = {
            "operation_id": "batch-bg-and-qr",
            "type": "BATCH",
            "target_ids": [],
            "expected_document_version": 2,
            "reason": "change background but accidentally move QR",
            "payload": {
                "atomic": True,
                "operations": [
                    {
                        "operation_id": "background-black",
                        "type": "SET_PROPERTY",
                        "target_ids": ["frame"],
                        "expected_document_version": 2,
                        "payload": {"path": "frame.background.color", "value": "#000000"},
                        "reason": "background black",
                    },
                    {
                        "operation_id": "qr-move",
                        "type": "MOVE_NODE",
                        "target_ids": ["qr"],
                        "expected_document_version": 2,
                        "payload": {"x": 500, "y": 1300},
                        "reason": "must be blocked",
                    },
                ],
            },
        }
        result = preflight(
            document,
            operation,
            (qr_lock,),
            current_document_version=2,
        )
        self.assertEqual(result.decision, "DENY")
        self.assertEqual(document, before)
        self.assertEqual(result.violations[0].constraint_id, "qr-lock")

    def test_soft_style_lock_warns_but_allows(self) -> None:
        document = fixture("single-frame-poster")
        document["resources"]["styles"]["style-new"] = {"id": "style-new", "kind": "STYLE"}
        style_lock = constraint(
            "style-soft",
            "LOCK_STYLE",
            "headline",
            severity="SOFT",
        )
        result = preflight(
            document,
            {
                "operation_id": "style-change",
                "type": "APPLY_STYLE",
                "target_ids": ["headline"],
                "expected_document_version": 1,
                "payload": {"style_id": "style-new", "mode": "APPEND"},
                "reason": "try style",
            },
            (style_lock,),
            current_document_version=1,
        )
        self.assertEqual(result.decision, "ALLOW_WITH_WARNINGS")
        self.assertEqual(len(result.warnings), 1)

    def test_qr_postflight_core_failure_is_repairable_but_quiet_zone_is_warning(self) -> None:
        qr = constraint(
            "scan-qr",
            "REQUIRE_SCANNABILITY",
            "qr",
            parameters={"expected_payload_hash": "abc"},
        )
        warning = postflight(
            (qr,),
            {
                "scan-qr": PostflightEvidence(
                    constraint_id="scan-qr",
                    kind="qr",
                    passed=True,
                    actual={
                        "detected": True,
                        "decoded": True,
                        "payload_match": True,
                        "quiet_zone_ok": False,
                        "size_ok": True,
                    },
                    repairable=True,
                )
            },
        )
        self.assertEqual(warning.outcome, "PASS")
        self.assertEqual(warning.warnings[0].message_code, "CONSTRAINT_QR_QUIET_ZONE_WARNING")

        failed = postflight(
            (qr,),
            {
                "scan-qr": PostflightEvidence(
                    constraint_id="scan-qr",
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
            },
        )
        self.assertEqual(failed.outcome, "FAIL_REPAIRABLE")
        self.assertEqual(failed.violations[0].message_code, "CONSTRAINT_QR_NOT_SCANNABLE")

    def test_protected_region_postflight_diff_requires_evidence(self) -> None:
        protected = constraint(
            "protect-logo",
            "PROTECT_REGION",
            "logo",
            parameters={"max_diff": 0.01},
        )
        missing = postflight((protected,), {})
        self.assertEqual(missing.outcome, "FAIL_HARD")
        self.assertEqual(missing.violations[0].message_code, "CONSTRAINT_EVIDENCE_MISSING")

        failed = postflight(
            (protected,),
            {
                "protect-logo": PostflightEvidence(
                    constraint_id="protect-logo",
                    kind="protected_region_diff",
                    passed=False,
                    actual={"diff_ratio": 0.12},
                    repairable=True,
                )
            },
        )
        self.assertEqual(failed.outcome, "FAIL_REPAIRABLE")
        self.assertEqual(
            failed.violations[0].message_code,
            "CONSTRAINT_PROTECTED_REGION_DIFF_EXCEEDED",
        )

    def test_authorized_override_is_audited_and_safety_rule_cannot_override(self) -> None:
        locked = constraint("lock-headline", "LOCK_POSITION", "headline")
        audit = create_override_audit(
            locked,
            override_id="override-1",
            actor_id="user-1",
            reason="approved exception for this revision",
            authorized=True,
        )
        result = preflight(
            fixture("single-frame-poster"),
            {
                "operation_id": "move-with-override",
                "type": "MOVE_NODE",
                "target_ids": ["headline"],
                "expected_document_version": 1,
                "payload": {"x": 99, "y": 99},
                "reason": "approved override",
            },
            (locked,),
            current_document_version=1,
            overrides={locked.id: audit},
        )
        self.assertEqual(result.decision, "ALLOW")
        self.assertEqual(audit.constraint_id, locked.id)
        self.assertTrue(audit.reason)

        safety = constraint(
            "system-lock",
            "LOCK_POSITION",
            "headline",
            source="SAFETY_SYSTEM",
        )
        with self.assertRaises(OverrideDenied):
            create_override_audit(
                safety,
                override_id="override-2",
                actor_id="user-1",
                reason="not allowed",
                authorized=True,
            )

    def test_stale_document_version_is_preflight_denial(self) -> None:
        result = preflight(
            fixture("single-frame-poster"),
            {
                "operation_id": "stale",
                "type": "MOVE_NODE",
                "target_ids": ["headline"],
                "expected_document_version": 1,
                "payload": {"x": 1, "y": 1},
                "reason": "stale",
            },
            (),
            current_document_version=2,
        )
        self.assertEqual(result.decision, "DENY")
        self.assertEqual(result.violations[0].message_code, "CONSTRAINT_OPERATION_INVALID")

    def test_missing_constraint_target_is_hard_violation(self) -> None:
        missing = constraint("missing-target", "LOCK_POSITION", "does-not-exist")
        result = preflight(
            fixture("single-frame-poster"),
            {
                "operation_id": "move-headline",
                "type": "MOVE_NODE",
                "target_ids": ["headline"],
                "expected_document_version": 1,
                "payload": {"x": 61, "y": 80},
                "reason": "unrelated edit",
            },
            (missing,),
            current_document_version=1,
        )
        self.assertEqual(result.decision, "DENY")
        self.assertEqual(result.violations[0].message_code, "CONSTRAINT_TARGET_MISSING")

    def test_explicit_protection_compiler_and_snapshot_are_deterministic(self) -> None:
        protections = compile_user_explicit_protections(
            target_id="qr",
            protections=("transform", "content", "scannability"),
            id_prefix="user-instruction-1",
        )
        self.assertEqual([item.type for item in protections], ["LOCK_TRANSFORM", "LOCK_CONTENT", "REQUIRE_SCANNABILITY"])
        self.assertTrue(all(item.source == "USER_EXPLICIT" for item in protections))
        self.assertEqual(
            constraint_snapshot_hash(protections),
            constraint_snapshot_hash(tuple(reversed(protections))),
        )


if __name__ == "__main__":
    unittest.main()
