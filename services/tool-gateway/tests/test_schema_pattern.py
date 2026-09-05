from __future__ import annotations

import unittest
from uuid import uuid4

from lumi_tool_gateway.catalog import build_p0_registry
from lumi_tool_gateway.errors import ToolInputValidationError
from lumi_tool_gateway.schema import SchemaValidator


class SchemaPatternTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = SchemaValidator()
        self.registry = build_p0_registry()

    def test_asset_write_derived_accepts_canonical_refs(self) -> None:
        definition = self.registry.resolve("asset.write-derived", "1.0.0")
        self.validator.validate_input(
            definition.input_schema,
            {
                "source_asset_id": str(uuid4()),
                "artifact_ref": f"artifact://{uuid4()}",
                "metadata": {"purpose": "variant"},
            },
        )

    def test_asset_write_derived_rejects_malformed_refs_before_adapter(self) -> None:
        definition = self.registry.resolve("asset.write-derived", "1.0.0")
        with self.assertRaises(ToolInputValidationError):
            self.validator.validate_input(
                definition.input_schema,
                {
                    "source_asset_id": "not-a-uuid",
                    "artifact_ref": f"artifact://{uuid4()}",
                },
            )
        with self.assertRaises(ToolInputValidationError):
            self.validator.validate_input(
                definition.input_schema,
                {
                    "source_asset_id": str(uuid4()),
                    "artifact_ref": "https://example.com/not-canonical",
                },
            )

    def test_invalid_schema_pattern_fails_closed(self) -> None:
        with self.assertRaises(ToolInputValidationError):
            self.validator.validate_input(
                {"type": "string", "pattern": "["},
                "value",
            )


if __name__ == "__main__":
    unittest.main()
