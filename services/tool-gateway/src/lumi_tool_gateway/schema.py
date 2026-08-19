from __future__ import annotations

import re
from typing import Any

from .errors import ToolInputValidationError, ToolOutputValidationError


class SchemaValidator:
    """Small deterministic JSON-schema subset used at the Tool Gateway boundary."""

    def validate_input(self, schema: dict[str, Any], value: Any) -> None:
        self._validate(schema, value, path="$", output=False)

    def validate_output(self, schema: dict[str, Any], value: Any) -> None:
        self._validate(schema, value, path="$", output=True)

    def _fail(self, message: str, *, output: bool) -> None:
        error = ToolOutputValidationError if output else ToolInputValidationError
        raise error(message)

    def _validate(
        self,
        schema: dict[str, Any],
        value: Any,
        *,
        path: str,
        output: bool,
    ) -> None:
        if not isinstance(schema, dict):
            self._fail(f"{path}: schema must be an object", output=output)
        if "const" in schema and value != schema["const"]:
            self._fail(f"{path}: const mismatch", output=output)
        if "enum" in schema:
            enum = schema["enum"]
            if not isinstance(enum, list) or value not in enum:
                self._fail(f"{path}: enum mismatch", output=output)

        expected = schema.get("type")
        if expected is not None:
            self._validate_type(expected, value, path=path, output=output)

        if isinstance(value, dict):
            properties = schema.get("properties", {})
            if properties is not None and not isinstance(properties, dict):
                self._fail(f"{path}: properties must be object", output=output)
            required = schema.get("required", [])
            if required is not None and not isinstance(required, list):
                self._fail(f"{path}: required must be array", output=output)
            for key in required or []:
                if not isinstance(key, str) or key not in value:
                    self._fail(f"{path}.{key}: required", output=output)
            additional = schema.get("additionalProperties", True)
            for key, child in value.items():
                child_schema = (properties or {}).get(key)
                if child_schema is None:
                    if additional is False:
                        self._fail(f"{path}.{key}: additional property forbidden", output=output)
                    if isinstance(additional, dict):
                        self._validate(additional, child, path=f"{path}.{key}", output=output)
                    continue
                if not isinstance(child_schema, dict):
                    self._fail(f"{path}.{key}: property schema invalid", output=output)
                self._validate(child_schema, child, path=f"{path}.{key}", output=output)
            min_properties = schema.get("minProperties")
            max_properties = schema.get("maxProperties")
            if isinstance(min_properties, int) and len(value) < min_properties:
                self._fail(f"{path}: too few properties", output=output)
            if isinstance(max_properties, int) and len(value) > max_properties:
                self._fail(f"{path}: too many properties", output=output)

        if isinstance(value, list):
            min_items = schema.get("minItems")
            max_items = schema.get("maxItems")
            if isinstance(min_items, int) and len(value) < min_items:
                self._fail(f"{path}: too few items", output=output)
            if isinstance(max_items, int) and len(value) > max_items:
                self._fail(f"{path}: too many items", output=output)
            items = schema.get("items")
            if items is not None:
                if not isinstance(items, dict):
                    self._fail(f"{path}: items schema invalid", output=output)
                for index, child in enumerate(value):
                    self._validate(items, child, path=f"{path}[{index}]", output=output)

        if isinstance(value, str):
            min_length = schema.get("minLength")
            max_length = schema.get("maxLength")
            if isinstance(min_length, int) and len(value) < min_length:
                self._fail(f"{path}: string too short", output=output)
            if isinstance(max_length, int) and len(value) > max_length:
                self._fail(f"{path}: string too long", output=output)
            pattern = schema.get("pattern")
            if pattern is not None:
                if not isinstance(pattern, str):
                    self._fail(f"{path}: pattern must be string", output=output)
                try:
                    matched = re.search(pattern, value)
                except re.error:
                    self._fail(f"{path}: pattern invalid", output=output)
                    return
                if matched is None:
                    self._fail(f"{path}: string pattern mismatch", output=output)

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if isinstance(minimum, (int, float)) and value < minimum:
                self._fail(f"{path}: below minimum", output=output)
            if isinstance(maximum, (int, float)) and value > maximum:
                self._fail(f"{path}: above maximum", output=output)

    def _validate_type(
        self,
        expected: Any,
        value: Any,
        *,
        path: str,
        output: bool,
    ) -> None:
        if isinstance(expected, list):
            if any(self._matches_type(item, value) for item in expected if isinstance(item, str)):
                return
            self._fail(f"{path}: type mismatch", output=output)
            return
        if not isinstance(expected, str) or not self._matches_type(expected, value):
            self._fail(f"{path}: expected {expected}", output=output)

    @staticmethod
    def _matches_type(expected: str, value: Any) -> bool:
        return {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(expected, False)
