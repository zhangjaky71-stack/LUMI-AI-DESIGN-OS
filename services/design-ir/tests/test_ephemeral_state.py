from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/design-ir/src"))

from lumi_design_ir import StructuralValidationError, validate_document  # noqa: E402

CORPUS = json.loads(
    (ROOT / "contracts/design-ir/v1/fixtures/corpus.json").read_text(encoding="utf-8")
)


def poster() -> dict:
    for case in CORPUS["cases"]:
        if case["name"] == "single-frame-poster":
            return deepcopy(case["document"])
    raise AssertionError("single-frame-poster fixture missing")


class EphemeralStateTests(unittest.TestCase):
    def test_document_viewport_metadata_is_rejected(self) -> None:
        document = poster()
        document["metadata"]["viewport"] = {"zoom": 2}
        with self.assertRaises(StructuralValidationError):
            validate_document(document)

    def test_renderer_texture_metadata_is_rejected(self) -> None:
        document = poster()
        document["nodes"]["headline"]["metadata"]["pixi_texture_id"] = "texture-1"
        with self.assertRaises(StructuralValidationError):
            validate_document(document)


if __name__ == "__main__":
    unittest.main()
