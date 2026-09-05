from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lumi_api.api import create_contract_app

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "packages" / "api-client-v1" / "src" / "generated.ts"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _ref_name(reference: str) -> str:
    return reference.rsplit("/", 1)[-1]


def _ts_type(schema: dict[str, Any] | None) -> str:
    if not schema:
        return "unknown"
    if "$ref" in schema:
        return _ref_name(str(schema["$ref"]))
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if "enum" in schema:
        return " | ".join(json.dumps(item, ensure_ascii=False) for item in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(_ts_type(item) for item in schema["anyOf"])
    if "oneOf" in schema:
        return " | ".join(_ts_type(item) for item in schema["oneOf"])
    if "allOf" in schema:
        return " & ".join(_ts_type(item) for item in schema["allOf"])

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join("null" if item == "null" else _ts_type({"type": item}) for item in schema_type)
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        return f"Array<{_ts_type(schema.get('items'))}>"
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        fields: list[str] = []
        for name, property_schema in properties.items():
            optional = "" if name in required else "?"
            fields.append(f"  {json.dumps(name)}{optional}: {_ts_type(property_schema)};")
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            fields.append(f"  [key: string]: {_ts_type(additional)};")
        elif additional is True:
            fields.append("  [key: string]: unknown;")
        return "{\n" + "\n".join(fields) + "\n}"
    return "unknown"


def _component_types(openapi: dict[str, Any]) -> list[str]:
    schemas = openapi.get("components", {}).get("schemas", {})
    output: list[str] = []
    for name in sorted(schemas):
        output.append(f"export type {name} = {_ts_type(schemas[name])};")
    return output


def _parameter_type(parameters: list[dict[str, Any]], location: str) -> str:
    selected = [parameter for parameter in parameters if parameter.get("in") == location]
    if not selected:
        return "Record<string, never>"
    fields: list[str] = []
    for parameter in selected:
        optional = "" if parameter.get("required") else "?"
        fields.append(
            f"  {json.dumps(str(parameter['name']))}{optional}: "
            f"{_ts_type(parameter.get('schema'))};"
        )
    return "{\n" + "\n".join(fields) + "\n}"


def _request_body_type(operation: dict[str, Any]) -> str:
    body = operation.get("requestBody")
    if not isinstance(body, dict):
        return "undefined"
    content = body.get("content", {})
    json_content = content.get("application/json") or next(iter(content.values()), {})
    return _ts_type(json_content.get("schema"))


def _response_type(operation: dict[str, Any]) -> str:
    responses = operation.get("responses", {})
    for status in sorted(responses, key=str):
        if not str(status).startswith("2"):
            continue
        response = responses[status]
        content = response.get("content", {}) if isinstance(response, dict) else {}
        if not content:
            return "undefined"
        json_content = content.get("application/json") or next(iter(content.values()), {})
        return _ts_type(json_content.get("schema"))
    return "unknown"


def _operation_map(openapi: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, str]]]:
    definitions: list[str] = []
    runtime: dict[str, dict[str, str]] = {}
    for path in sorted(openapi.get("paths", {})):
        path_item = openapi["paths"][path]
        shared_parameters = list(path_item.get("parameters", []))
        for method in sorted(HTTP_METHODS):
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str):
                raise ValueError(f"operation without operationId: {method.upper()} {path}")
            parameters = shared_parameters + list(operation.get("parameters", []))
            definitions.append(
                "\n".join(
                    [
                        f"  {json.dumps(operation_id)}: {{",
                        f"    method: {json.dumps(method.upper())};",
                        f"    path: {json.dumps(path)};",
                        f"    pathParams: {_parameter_type(parameters, 'path')};",
                        f"    query: {_parameter_type(parameters, 'query')};",
                        f"    headers: {_parameter_type(parameters, 'header')};",
                        f"    body: {_request_body_type(operation)};",
                        f"    response: {_response_type(operation)};",
                        "  };",
                    ]
                )
            )
            runtime[operation_id] = {"method": method.upper(), "path": path}
    return definitions, runtime


def generated_source() -> str:
    openapi = create_contract_app().openapi()
    components = _component_types(openapi)
    operations, runtime = _operation_map(openapi)
    return "\n".join(
        [
            "// AUTO-GENERATED by scripts/generate_api_v1_client.py. DO NOT EDIT.",
            "/* eslint-disable */",
            "",
            *components,
            "",
            "export interface ApiV1OperationMap {",
            *operations,
            "}",
            "",
            "export const apiV1OperationSpec = "
            + json.dumps(runtime, indent=2, sort_keys=True)
            + " as const;",
            "",
            "export type ApiV1OperationId = keyof ApiV1OperationMap;",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = generated_source()
    output = args.output

    if args.check:
        if not output.exists():
            print(f"missing generated API client: {output}")
            return 1
        actual = output.read_text(encoding="utf-8")
        if actual != expected:
            print(f"generated API client is stale: {output}")
            return 1
        print(f"generated API client is current: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
