#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

_INLINE_LIMIT_BYTES = 64 * 1024
_S3_REF = re.compile(r"^s3ref://[^\s#]+#sha256=([0-9a-f]{64})$")


class OffloadProbeError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OffloadProbeError(message)


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OffloadProbeError(f"unable to read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise OffloadProbeError(f"{label} must be a JSON object")
    return payload


def _uuid(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(value), f"{label} must be a UUID")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise OffloadProbeError(f"{label} must be a UUID") from exc


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def validate_payload(
    probe: dict[str, Any],
    *,
    s3: dict[str, Any] | None = None,
) -> dict[str, Any]:
    calls = probe.get("calls")
    _require(isinstance(calls, dict), "probe calls are missing")
    normal = calls.get("sandbox.execute") if isinstance(calls, dict) else None
    _require(isinstance(normal, dict), "normal sandbox.execute call is missing")
    normal_request = normal.get("request") if isinstance(normal, dict) else None
    _require(isinstance(normal_request, dict), "normal sandbox.execute request is missing")
    normal_call_id = _uuid(normal_request.get("tool_call_id"), "normal sandbox tool_call_id")

    offload = probe.get("result_offload")
    _require(isinstance(offload, dict), "probe result_offload is missing")
    assert isinstance(offload, dict)
    _require(offload.get("tool") == "sandbox.execute", "offload tool must be sandbox.execute")
    offload_call_id = _uuid(offload.get("tool_call_id"), "offload tool_call_id")
    _require(offload_call_id != normal_call_id, "offload must use a separate sandbox tool_call_id")
    _require(offload.get("truncated") is True, "offload must be marked truncated")
    _require(
        offload.get("inline_data_present") is True,
        "raw probe must preserve the bounded inline preview",
    )

    result_ref = offload.get("result_ref")
    _require(isinstance(result_ref, str), "offload result_ref is missing")
    match = _S3_REF.fullmatch(result_ref or "")
    _require(match is not None, "offload result_ref must be s3ref://...#sha256=...")

    result = offload.get("result")
    _require(isinstance(result, dict), "offload ToolResult snapshot is missing")
    assert isinstance(result, dict)
    _require(
        _uuid(result.get("tool_call_id"), "offload result tool_call_id") == offload_call_id,
        "offload ToolResult tool_call_id differs from request",
    )
    _require(result.get("truncated") is True, "offload ToolResult must be truncated")
    _require(
        result.get("full_result_ref") == result_ref,
        "offload ToolResult full_result_ref differs from result_ref",
    )
    preview = result.get("data")
    _require(preview is not None, "offload ToolResult inline preview is missing")
    preview_bytes = len(_canonical_bytes(preview))
    _require(preview_bytes > 0, "offload inline preview must not be empty")
    _require(
        preview_bytes <= _INLINE_LIMIT_BYTES,
        "offload inline preview exceeds Tool Gateway inline limit",
    )

    serialized_result_bytes: int | None = None
    if s3 is not None:
        _require(s3.get("result_ref") == result_ref, "S3 result_ref differs from raw probe")
        inline_limit = s3.get("inline_limit_bytes")
        _require(
            inline_limit == _INLINE_LIMIT_BYTES,
            "S3 evidence inline limit differs from Tool Gateway contract",
        )
        serialized_result_bytes = s3.get("content_length")
        _require(
            isinstance(serialized_result_bytes, int)
            and serialized_result_bytes > _INLINE_LIMIT_BYTES,
            "offloaded serialized result must exceed inline limit",
        )
        assert isinstance(serialized_result_bytes, int)
        _require(
            preview_bytes < serialized_result_bytes,
            "bounded inline preview must be smaller than the offloaded full payload",
        )

    return {
        "schema_version": 1,
        "tool": "sandbox.execute",
        "normal_tool_call_id": normal_call_id,
        "offload_tool_call_id": offload_call_id,
        "truncated": True,
        "inline_preview_present": True,
        "inline_preview_bytes": preview_bytes,
        "inline_limit_bytes": _INLINE_LIMIT_BYTES,
        "full_payload_inline_present": False,
        "result_ref": result_ref,
        "sha256": match.group(1) if match is not None else "",
        "serialized_result_bytes": serialized_result_bytes,
    }


def _fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    normal_id = "11111111-1111-4111-8111-111111111111"
    offload_id = "22222222-2222-4222-8222-222222222222"
    digest = "a" * 64
    ref = f"s3ref://lumi-staging-123456789012-us-east-1-exports/tool-results/v1/test#sha256={digest}"
    result = {
        "tool_call_id": offload_id,
        "status": "succeeded",
        "resolved_name": "sandbox.execute",
        "resolved_version": "1.0.0",
        "summary": "Full tool result stored outside Agent context.",
        "resource_refs": [],
        "truncated": True,
        "full_result_ref": ref,
        "replayed": False,
        "approval_id": None,
        "error_code": None,
        "data": {"stdout": "x" * 1024 + "…", "stderr": "", "exit_code": 0},
    }
    probe = {
        "calls": {
            "sandbox.execute": {
                "request": {"tool_call_id": normal_id},
                "result": {"data": {"exit_code": 0}},
            }
        },
        "result_offload": {
            "tool": "sandbox.execute",
            "tool_call_id": offload_id,
            "result_ref": ref,
            "inline_data_present": True,
            "truncated": True,
            "result": result,
        },
    }
    s3 = {
        "result_ref": ref,
        "content_length": 70000,
        "inline_limit_bytes": _INLINE_LIMIT_BYTES,
    }
    return probe, s3


def _must_fail(label: str, probe: dict[str, Any], s3: dict[str, Any]) -> None:
    try:
        validate_payload(probe, s3=s3)
    except OffloadProbeError:
        return
    raise RuntimeError(f"offload probe self-test accepted invalid evidence: {label}")


def self_test() -> None:
    probe, s3 = _fixture()
    facts = validate_payload(probe, s3=s3)
    _require(facts["inline_preview_present"] is True, "self-test preview fact missing")
    _require(facts["full_payload_inline_present"] is False, "self-test full payload fact invalid")

    broken = copy.deepcopy(probe)
    broken["result_offload"]["truncated"] = False
    _must_fail("not truncated", broken, s3)

    broken = copy.deepcopy(probe)
    broken["result_offload"]["inline_data_present"] = False
    _must_fail("preview removed", broken, s3)

    broken = copy.deepcopy(probe)
    broken["result_offload"]["tool_call_id"] = probe["calls"]["sandbox.execute"]["request"]["tool_call_id"]
    _must_fail("reused normal sandbox call id", broken, s3)

    broken_s3 = copy.deepcopy(s3)
    broken_s3["content_length"] = 1024
    _must_fail("small offload object", probe, broken_s3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--s3", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("Tool Gateway P0 offload probe contract: PASS")
        return 0
    if args.probe is None:
        raise SystemExit("--probe is required unless --self-test is used")
    try:
        probe = _load(args.probe, "Tool Gateway probe")
        s3 = _load(args.s3, "Tool Gateway S3 evidence") if args.s3 is not None else None
        facts = validate_payload(probe, s3=s3)
    except OffloadProbeError as exc:
        raise SystemExit(f"Tool Gateway P0 offload probe contract failed: {exc}") from exc
    print(json.dumps(facts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
