#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^[1-9][0-9]*$")


class DecisionBindingError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionBindingError(f"unable to read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DecisionBindingError(f"{path} must contain a JSON object")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DecisionBindingError(message)


def validate_binding(decision: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    _require(decision.get("schema_version") == 1, "NODE-71 decision schema_version must be 1")
    _require(decision.get("passed") is True, "runtime-image sealing requires passed=true NODE-71 decision")
    rc = decision.get("release_candidate")
    _require(isinstance(rc, dict), "NODE-71 decision release_candidate is missing")
    git_sha = rc.get("git_sha")
    _require(isinstance(git_sha, str) and bool(SHA40.fullmatch(git_sha.lower())), "NODE-71 decision git_sha is invalid")
    _require(binding.get("status") == "PASS", "runtime-image binding status must be PASS")
    _require(binding.get("git_sha") == git_sha.lower(), "runtime-image binding git_sha differs from NODE-71 decision")
    _require(binding.get("version") == rc.get("version"), "runtime-image binding version differs from NODE-71 decision")
    build_run_id = binding.get("build_run_id")
    _require(isinstance(build_run_id, str) and bool(RUN_ID.fullmatch(build_run_id)), "runtime-image binding build_run_id is invalid")
    image_set_ref = binding.get("container_image_set_ref")
    _require(
        isinstance(image_set_ref, str) and image_set_ref == rc.get("container_image_set_ref"),
        "runtime-image binding artifact ref differs from NODE-71 decision",
    )
    report_sha = binding.get("attestation_report_sha256")
    _require(isinstance(report_sha, str) and bool(SHA256.fullmatch(report_sha)), "runtime-image binding attestation report SHA-256 is invalid")
    source_digest = binding.get("attestation_source_digest")
    _require(source_digest == git_sha.lower(), "runtime-image attestation source digest differs from NODE-71 RC SHA")
    _require(binding.get("runtime_count") == 6, "runtime-image binding must cover exactly six runtimes")
    return {
        "status": "PASS",
        "git_sha": git_sha.lower(),
        "version": rc.get("version"),
        "build_run_id": build_run_id,
        "container_image_set_ref": image_set_ref,
        "attestation_report_sha256": report_sha,
        "attestation_source_digest": source_digest,
        "runtime_count": 6,
    }


def _decision_id_payload(decision: dict[str, Any]) -> dict[str, Any]:
    canonical = copy.deepcopy(decision)
    canonical.pop("decision_id", None)
    canonical.pop("passed", None)
    return canonical


def seal_decision(decision: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_binding(decision, binding)
    sealed = copy.deepcopy(decision)
    sealed["runtime_image_binding"] = normalized
    canonical = json.dumps(
        _decision_id_payload(sealed),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    sealed["decision_id"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    sealed["passed"] = True
    return sealed


def _rewrite_markdown(path: Path, sealed: dict[str, Any]) -> None:
    if not path.is_file():
        raise DecisionBindingError(f"NODE-71 decision markdown is missing: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    decision_id = sealed["decision_id"]
    binding = sealed["runtime_image_binding"]
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith("- Decision ID: "):
            output.append(f"- Decision ID: `{decision_id}`")
            output.append(
                "- Runtime image attestation: **PASS** "
                f"(build run `{binding['build_run_id']}`, source `{binding['attestation_source_digest']}`)"
            )
            replaced = True
        else:
            output.append(line)
    _require(replaced, "NODE-71 decision markdown Decision ID line is missing")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def self_test() -> dict[str, Any]:
    git_sha = "a" * 40
    decision = {
        "schema_version": 1,
        "manifest_id": "node71-contract",
        "release_candidate": {
            "git_sha": git_sha,
            "version": "1.0.0-rc.contract",
            "container_image_set_ref": (
                "https://github.com/example/lumi/actions/runs/123"
                f"#artifact=runtime-image-set-{git_sha}/container-image-set.json"
            ),
        },
        "container_image_set": {"images": {}, "provenance": {}},
        "summary": {},
        "checks": [],
        "parity_checks": [],
        "blockers": [],
        "approvals": {},
        "decision_id": "pre-binding-id",
        "passed": True,
    }
    binding = {
        "status": "PASS",
        "git_sha": git_sha,
        "version": "1.0.0-rc.contract",
        "build_run_id": "123",
        "container_image_set_ref": decision["release_candidate"]["container_image_set_ref"],
        "attestation_report_sha256": "b" * 64,
        "attestation_source_digest": git_sha,
        "runtime_count": 6,
    }
    sealed = seal_decision(decision, binding)
    _require(sealed["runtime_image_binding"] == binding, "clean binding was not sealed exactly")
    _require(sealed["decision_id"] != decision["decision_id"], "decision_id must cover runtime-image binding")

    drills: list[str] = []

    def must_block(label: str, mutation: Callable[[dict[str, Any]], None]) -> None:
        candidate = copy.deepcopy(binding)
        mutation(candidate)
        try:
            seal_decision(decision, candidate)
        except DecisionBindingError:
            drills.append(label)
            return
        raise DecisionBindingError(f"negative drill did not block: {label}")

    must_block("binding_status_swap_blocked", lambda value: value.__setitem__("status", "FAIL"))
    must_block("binding_sha_swap_blocked", lambda value: value.__setitem__("git_sha", "c" * 40))
    must_block("binding_build_run_zero_blocked", lambda value: value.__setitem__("build_run_id", "0"))
    must_block("binding_artifact_ref_swap_blocked", lambda value: value.__setitem__("container_image_set_ref", "other"))
    must_block("binding_report_hash_invalid_blocked", lambda value: value.__setitem__("attestation_report_sha256", "bad"))
    must_block("binding_source_sha_swap_blocked", lambda value: value.__setitem__("attestation_source_digest", "d" * 40))
    must_block("binding_runtime_count_swap_blocked", lambda value: value.__setitem__("runtime_count", 5))

    with tempfile.TemporaryDirectory(prefix="lumi-node71-binding-") as temp_dir:
        markdown = Path(temp_dir) / "decision.md"
        markdown.write_text(
            "# NODE-71 Staging Acceptance Decision\n\n"
            "- Status: **PASS**\n"
            "- Decision ID: `pre-binding-id`\n",
            encoding="utf-8",
        )
        _rewrite_markdown(markdown, sealed)
        rendered = markdown.read_text(encoding="utf-8")
        _require(sealed["decision_id"] in rendered, "markdown decision id was not resealed")
        _require("Runtime image attestation: **PASS**" in rendered, "markdown attestation seal is missing")

    return {
        "status": "PASS",
        "decision_id_resealed": True,
        "runtime_image_binding": sealed["runtime_image_binding"],
        "negative_drills": drills,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seal verified runtime-image attestation identity into a passed NODE-71 decision"
    )
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    if args.decision is None or args.binding is None:
        raise DecisionBindingError("--decision and --binding are required unless --self-test is used")
    decision = _load(args.decision)
    binding = _load(args.binding)
    sealed = seal_decision(decision, binding)
    _write(args.decision, sealed)
    if args.markdown is not None:
        _rewrite_markdown(args.markdown, sealed)
    print(
        json.dumps(
            {
                "status": "PASS",
                "decision_id": sealed["decision_id"],
                "runtime_image_binding": sealed["runtime_image_binding"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DecisionBindingError as exc:
        raise SystemExit(f"NODE-71 runtime-image decision binding failed: {exc}") from exc
