#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from validate_tool_gateway_e2e_evidence import (
    ToolGatewayE2EEvidenceError,
    validate_contract,
    validate_evidence,
)


class ToolGatewayE2EMergeError(RuntimeError):
    pass


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolGatewayE2EMergeError(f"unable to read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ToolGatewayE2EMergeError(f"{label} must be a JSON object")
    return payload


def merge(
    staging: dict[str, Any],
    tool_gateway_e2e: dict[str, Any],
) -> dict[str, Any]:
    if "tool_gateway_e2e" in staging:
        raise ToolGatewayE2EMergeError(
            "staging evidence already contains tool_gateway_e2e; refuse implicit overwrite"
        )
    try:
        validate_contract(tool_gateway_e2e)
    except ToolGatewayE2EEvidenceError as exc:
        raise ToolGatewayE2EMergeError(
            f"Tool Gateway E2E contract is not releasable: {exc}"
        ) from exc
    merged = copy.deepcopy(staging)
    merged["tool_gateway_e2e"] = copy.deepcopy(tool_gateway_e2e)
    try:
        validate_evidence(merged)
    except ToolGatewayE2EEvidenceError as exc:
        raise ToolGatewayE2EMergeError(
            f"Tool Gateway E2E evidence does not bind to staging RC: {exc}"
        ) from exc
    return merged


def _output_path(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.suffix != ".json":
        raise ToolGatewayE2EMergeError("output must be a JSON file")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--tool-e2e", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    staging_path = args.staging.resolve()
    tool_path = args.tool_e2e.resolve()
    output_path = _output_path(args.output)
    if output_path in {staging_path, tool_path}:
        raise SystemExit("output must not overwrite either input evidence file")

    try:
        merged = merge(
            _load(staging_path, "staging evidence"),
            _load(tool_path, "Tool Gateway E2E evidence"),
        )
    except ToolGatewayE2EMergeError as exc:
        raise SystemExit(f"Tool Gateway E2E evidence merge failed: {exc}") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(merged, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
