#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

from assemble_tool_gateway_p0_e2e_evidence import (
    AssembleError,
    _input_ref,
    _load,
    _write,
    assemble,
)
from merge_tool_gateway_e2e_into_staging_evidence import merge
from validate_tool_gateway_p0_offload_probe import OffloadProbeError, validate_payload


class AssembleV2Error(RuntimeError):
    pass


def assemble_v2(
    *,
    staging: dict[str, Any],
    probe: dict[str, Any],
    db: dict[str, Any],
    s3: dict[str, Any],
    readiness: dict[str, Any],
    search: dict[str, Any],
    refs: dict[str, str],
) -> dict[str, Any]:
    try:
        facts = validate_payload(probe, s3=s3)
    except OffloadProbeError as exc:
        raise AssembleV2Error(f"raw offload probe semantics are invalid: {exc}") from exc

    # The v1 assembler predates Tool Gateway's deliberate bounded inline preview.
    # Feed it a compatibility view only after proving that the real raw probe is
    # truncated, preview-bounded and backed by a durable full_result_ref.
    compatibility_probe = copy.deepcopy(probe)
    compatibility_offload = compatibility_probe.get("result_offload")
    if not isinstance(compatibility_offload, dict):
        raise AssembleV2Error("result_offload disappeared from compatibility probe")
    compatibility_offload["inline_data_present"] = False

    try:
        payload = assemble(
            staging=staging,
            probe=compatibility_probe,
            db=db,
            s3=s3,
            readiness=readiness,
            search=search,
            refs=refs,
        )
    except AssembleError as exc:
        raise AssembleV2Error(str(exc)) from exc

    result_offload = payload.get("result_offload")
    if not isinstance(result_offload, dict):
        raise AssembleV2Error("assembled result_offload is missing")
    result_offload.update(
        {
            "semantics_version": 2,
            "truncated": True,
            "inline_preview_present": True,
            "inline_preview_bytes": facts["inline_preview_bytes"],
            "full_payload_inline_present": False,
            # Retained for v1 validator compatibility. In v2 this means the
            # complete payload is not inline; a bounded preview is explicitly
            # represented by inline_preview_present/inline_preview_bytes.
            "inline_data_present": False,
        }
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--s3", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--search", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--merged-output", type=Path)
    args = parser.parse_args()

    inputs = {
        "staging": args.staging.resolve(),
        "probe": args.probe.resolve(),
        "db": args.db.resolve(),
        "s3": args.s3.resolve(),
        "readiness": args.readiness.resolve(),
        "search": args.search.resolve(),
    }
    output = args.output.resolve()
    if output in inputs.values():
        raise SystemExit("output must not overwrite an input evidence file")
    if args.merged_output is not None and args.merged_output.resolve() in {
        *inputs.values(),
        output,
    }:
        raise SystemExit("merged-output must be a new file")

    refs = {key: _input_ref(path) for key, path in inputs.items() if key != "staging"}
    try:
        staging = _load(inputs["staging"], "parent staging evidence")
        assembled = assemble_v2(
            staging=staging,
            probe=_load(inputs["probe"], "Agent Runtime probe"),
            db=_load(inputs["db"], "PostgreSQL evidence"),
            s3=_load(inputs["s3"], "S3 evidence"),
            readiness=_load(inputs["readiness"], "readiness evidence"),
            search=_load(inputs["search"], "search evidence"),
            refs=refs,
        )
        _write(output, assembled)
        if args.merged_output is not None:
            merged = merge(staging, assembled)
            _write(args.merged_output.resolve(), merged)
    except (AssembleV2Error, AssembleError) as exc:
        raise SystemExit(f"Tool Gateway P0 evidence assembly v2 failed: {exc}") from exc

    print(output)
    if args.merged_output is not None:
        print(args.merged_output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
