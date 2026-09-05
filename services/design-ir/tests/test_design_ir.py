from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/design-ir/src"))

from lumi_design_ir import (  # noqa: E402
    DocumentVersionConflict,
    OperationError,
    StructuralValidationError,
    apply_operation,
    codepoint_length,
    content_hash,
    slice_codepoints,
    validate_document,
)

CORPUS = json.loads(
    (ROOT / "contracts/design-ir/v1/fixtures/corpus.json").read_text(encoding="utf-8")
)


def fixture(name: str) -> dict:
    for case in CORPUS["cases"]:
        if case["name"] == name:
            return deepcopy(case["document"])
    raise KeyError(name)


class DesignIRContractTests(unittest.TestCase):
    def test_fixture_corpus_has_required_breadth(self) -> None:
        names = {case["name"] for case in CORPUS["cases"]}
        self.assertGreaterEqual(len(names), 10)
        self.assertTrue(
            {
                "single-frame-poster",
                "multi-frame-social-kit",
                "logo-and-qr-locks",
                "chinese-text-codepoints",
                "group-mask",
                "image-crop",
                "component-instance",
                "invalid-parent-cycle",
                "missing-asset-reference",
                "v1-migration-fixture",
            }.issubset(names)
        )

    def test_all_valid_fixtures_pass_reference_validation(self) -> None:
        for case in CORPUS["cases"]:
            if case["expect"] == "valid":
                validate_document(case["document"])

    def test_unicode_ranges_use_code_points_not_utf16_units(self) -> None:
        text = "你好👋设计"
        self.assertEqual(codepoint_length(text), 5)
        self.assertEqual(slice_codepoints(text, 2, 3), "👋")

    def test_canonical_hash_ignores_key_order_and_ephemeral_metadata(self) -> None:
        document = fixture("single-frame-poster")
        baseline = content_hash(document)
        reordered = dict(reversed(list(document.items())))
        self.assertEqual(content_hash(reordered), baseline)

        document["metadata"]["viewport"] = {"x": 10, "y": 20, "zoom": 2}
        document["nodes"]["headline"]["metadata"]["hover"] = True
        self.assertEqual(content_hash(document), baseline)

    def test_move_operation_is_deterministic_and_does_not_mutate_input(self) -> None:
        document = fixture("single-frame-poster")
        before = deepcopy(document)
        operation = {
            "operation_id": "op-move-headline",
            "type": "MOVE_NODE",
            "target_ids": ["headline"],
            "expected_document_version": 12,
            "payload": {"x": 88, "y": 144},
            "reason": "user requested title move",
        }
        first = apply_operation(document, operation, current_version=12)
        second = apply_operation(document, operation, current_version=12)
        self.assertEqual(document, before)
        self.assertEqual(first.document, second.document)
        self.assertEqual(first.after_hash, second.after_hash)
        self.assertEqual(first.document_version, 13)
        self.assertEqual(first.document["nodes"]["headline"]["transform"]["x"], 88)

    def test_stale_expected_version_is_rejected(self) -> None:
        operation = {
            "operation_id": "op-stale",
            "type": "MOVE_NODE",
            "target_ids": ["headline"],
            "expected_document_version": 11,
            "payload": {"x": 1, "y": 1},
            "reason": "stale client",
        }
        with self.assertRaises(DocumentVersionConflict):
            apply_operation(fixture("single-frame-poster"), operation, current_version=12)

    def test_batch_is_all_or_nothing_when_a_child_fails(self) -> None:
        document = fixture("single-frame-poster")
        before = deepcopy(document)
        operation = {
            "operation_id": "batch-atomic",
            "type": "BATCH",
            "target_ids": [],
            "expected_document_version": 3,
            "reason": "atomic edit",
            "payload": {
                "atomic": True,
                "operations": [
                    {
                        "operation_id": "move-first",
                        "type": "MOVE_NODE",
                        "target_ids": ["headline"],
                        "expected_document_version": 3,
                        "payload": {"x": 999, "y": 999},
                        "reason": "first child",
                    },
                    {
                        "operation_id": "invalid-asset-target",
                        "type": "REPLACE_ASSET",
                        "target_ids": ["headline"],
                        "expected_document_version": 3,
                        "payload": {"asset_id": "asset-nope"},
                        "reason": "must fail",
                    },
                ],
            },
        }
        with self.assertRaises(OperationError):
            apply_operation(document, operation, current_version=3)
        self.assertEqual(document, before)

    def test_reparent_that_creates_cycle_is_rejected_atomically(self) -> None:
        document = fixture("single-frame-poster")
        before = deepcopy(document)
        operation = {
            "operation_id": "op-cycle",
            "type": "REPARENT_NODE",
            "target_ids": ["frame"],
            "expected_document_version": 1,
            "payload": {"parent_id": "headline", "index": 0},
            "reason": "invalid cycle",
        }
        with self.assertRaises(StructuralValidationError):
            apply_operation(document, operation, current_version=1)
        self.assertEqual(document, before)

    def test_set_property_cannot_bypass_structural_operations(self) -> None:
        operation = {
            "operation_id": "op-bypass",
            "type": "SET_PROPERTY",
            "target_ids": ["headline"],
            "expected_document_version": 1,
            "payload": {"path": "parent_id", "value": "root"},
            "reason": "must use REPARENT_NODE",
        }
        with self.assertRaises(OperationError):
            apply_operation(fixture("single-frame-poster"), operation, current_version=1)


if __name__ == "__main__":
    unittest.main()
