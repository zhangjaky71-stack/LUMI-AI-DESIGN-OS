#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "staging" / "acceptance" / "media-generation-e2e-v1.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise EvidenceError(f"{path} must contain a JSON object")
    return raw


def required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip().upper() == "PENDING":
        raise EvidenceError(f"{name} is missing/PENDING")
    return value.strip()


def required_uuid(value: Any, name: str) -> UUID:
    raw = required_string(value, name)
    try:
        return UUID(raw)
    except ValueError as exc:
        raise EvidenceError(f"{name} must be a UUID") from exc


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != 1:
        raise EvidenceError("media generation E2E contract schema_version must be 1")
    if contract.get("scenario_id") != "E2E-03":
        raise EvidenceError("media generation E2E contract must bind E2E-03")
    if contract.get("required_status") != "PASS":
        raise EvidenceError("media generation E2E contract must require PASS")
    job_contract = contract.get("job_contract")
    if not isinstance(job_contract, dict):
        raise EvidenceError("media generation E2E job_contract is missing")
    expected = {
        "job_kind": "image.transform",
        "outbox_event_name": "job.dispatch.requested",
        "task_name": "lumi.jobs.image.transform",
        "queue": "lumi.media.image",
    }
    if job_contract != expected:
        raise EvidenceError("media generation E2E job contract drifted from canonical dispatch")
    terminal = contract.get("required_terminal_state")
    if terminal != {"task_status": "succeeded", "generation_status": "succeeded"}:
        raise EvidenceError("media generation E2E terminal state must require task/generation succeeded")
    stages = contract.get("required_evidence_stages")
    expected_stages = [
        "api_request",
        "generation_row",
        "task_row",
        "outbox_dispatch",
        "worker_execution",
        "artifact",
        "provenance",
    ]
    if stages != expected_stages:
        raise EvidenceError("media generation E2E required evidence stages drifted")


def validate_evidence(contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    validate_contract(contract)
    rc = evidence.get("release_candidate")
    if not isinstance(rc, dict):
        raise EvidenceError("release_candidate object is missing")
    rc_sha = required_string(rc.get("git_sha"), "release_candidate.git_sha").lower()
    if not SHA40.fullmatch(rc_sha):
        raise EvidenceError("release_candidate.git_sha must be an exact 40-character SHA")

    results = evidence.get("scenario_results")
    if not isinstance(results, dict):
        raise EvidenceError("scenario_results object is missing")
    scenario = results.get(contract["scenario_id"])
    if not isinstance(scenario, dict):
        raise EvidenceError("scenario_results.E2E-03 is missing")
    if scenario.get("status") != contract["required_status"]:
        raise EvidenceError("E2E-03 must be evidenced PASS")
    required_string(scenario.get("actual"), "E2E-03.actual")
    required_string(scenario.get("evidence_ref"), "E2E-03.evidence_ref")
    required_string(scenario.get("owner"), "E2E-03.owner")

    observed = scenario.get("media_generation")
    if not isinstance(observed, dict):
        raise EvidenceError("E2E-03.media_generation object is missing")

    request_id = required_string(observed.get("request_id"), "E2E-03.media_generation.request_id")
    trace_id = required_string(observed.get("trace_id"), "E2E-03.media_generation.trace_id")
    organization_id = required_uuid(observed.get("organization_id"), "E2E-03.media_generation.organization_id")
    project_id = required_uuid(observed.get("project_id"), "E2E-03.media_generation.project_id")
    task_id = required_uuid(observed.get("task_id"), "E2E-03.media_generation.task_id")
    generation_id = required_uuid(observed.get("generation_id"), "E2E-03.media_generation.generation_id")
    operation_id = required_uuid(observed.get("operation_id"), "E2E-03.media_generation.operation_id")
    outbox_event_id = required_uuid(observed.get("outbox_event_id"), "E2E-03.media_generation.outbox_event_id")
    artifact_id = required_uuid(observed.get("artifact_id"), "E2E-03.media_generation.artifact_id")
    artifact_version_id = required_uuid(
        observed.get("artifact_version_id"), "E2E-03.media_generation.artifact_version_id"
    )
    provenance_id = required_uuid(observed.get("provenance_id"), "E2E-03.media_generation.provenance_id")

    expected_outbox_id = uuid5(operation_id, f"lumi:image-transform-dispatch:{task_id}")
    if outbox_event_id != expected_outbox_id:
        raise EvidenceError("E2E-03 outbox_event_id does not match canonical deterministic dispatch ID")

    job_contract = contract["job_contract"]
    for field, expected in job_contract.items():
        if observed.get(field) != expected:
            raise EvidenceError(f"E2E-03.media_generation.{field} must equal {expected!r}")

    terminal = contract["required_terminal_state"]
    for field, expected in terminal.items():
        if observed.get(field) != expected:
            raise EvidenceError(f"E2E-03.media_generation.{field} must equal {expected!r}")

    if required_string(
        observed.get("provenance_code_git_sha"),
        "E2E-03.media_generation.provenance_code_git_sha",
    ).lower() != rc_sha:
        raise EvidenceError("E2E-03 provenance_code_git_sha must equal accepted RC SHA")

    storage_ref = required_string(observed.get("storage_ref"), "E2E-03.media_generation.storage_ref")
    if not storage_ref.startswith("s3://"):
        raise EvidenceError("E2E-03 storage_ref must be a durable s3:// reference")

    broker = observed.get("broker_message")
    if not isinstance(broker, dict):
        raise EvidenceError("E2E-03.media_generation.broker_message object is missing")
    broker_expected = {
        "job_id": str(task_id),
        "organization_id": str(organization_id),
        "project_id": str(project_id),
        "operation_id": str(operation_id),
        "trace_id": trace_id,
    }
    if broker != broker_expected:
        raise EvidenceError("E2E-03 broker_message does not match canonical identifier-only envelope")

    stages = observed.get("evidence")
    if not isinstance(stages, dict):
        raise EvidenceError("E2E-03.media_generation.evidence object is missing")
    required_stages = contract["required_evidence_stages"]
    if set(stages) != set(required_stages):
        raise EvidenceError("E2E-03 evidence stages must match the canonical required set exactly")
    for stage_name in required_stages:
        stage = stages.get(stage_name)
        if not isinstance(stage, dict):
            raise EvidenceError(f"E2E-03 evidence stage {stage_name} must be an object")
        required_string(stage.get("ref"), f"E2E-03.evidence.{stage_name}.ref")
        digest = required_string(stage.get("sha256"), f"E2E-03.evidence.{stage_name}.sha256").lower()
        if not SHA256.fullmatch(digest):
            raise EvidenceError(f"E2E-03 evidence stage {stage_name} sha256 must be 64 lowercase hex")

    return {
        "status": "PASS",
        "scenario_id": contract["scenario_id"],
        "request_id": request_id,
        "trace_id": trace_id,
        "organization_id": str(organization_id),
        "project_id": str(project_id),
        "task_id": str(task_id),
        "generation_id": str(generation_id),
        "operation_id": str(operation_id),
        "outbox_event_id": str(outbox_event_id),
        "artifact_id": str(artifact_id),
        "artifact_version_id": str(artifact_version_id),
        "provenance_id": str(provenance_id),
        "release_git_sha": rc_sha,
        "storage_ref": storage_ref,
        "evidence_stage_count": len(required_stages),
    }


def self_test(contract: dict[str, Any]) -> None:
    operation_id = UUID("11111111-1111-4111-8111-111111111111")
    task_id = UUID("22222222-2222-4222-8222-222222222222")
    organization_id = UUID("33333333-3333-4333-8333-333333333333")
    project_id = UUID("44444444-4444-4444-8444-444444444444")
    trace_id = "trace-e2e-contract"
    digest = "a" * 64
    observed = {
        "request_id": "request-e2e-contract",
        "trace_id": trace_id,
        "organization_id": str(organization_id),
        "project_id": str(project_id),
        "task_id": str(task_id),
        "generation_id": "55555555-5555-4555-8555-555555555555",
        "operation_id": str(operation_id),
        "outbox_event_id": str(uuid5(operation_id, f"lumi:image-transform-dispatch:{task_id}")),
        "artifact_id": "66666666-6666-4666-8666-666666666666",
        "artifact_version_id": "77777777-7777-4777-8777-777777777777",
        "provenance_id": "88888888-8888-4888-8888-888888888888",
        "job_kind": "image.transform",
        "outbox_event_name": "job.dispatch.requested",
        "task_name": "lumi.jobs.image.transform",
        "queue": "lumi.media.image",
        "task_status": "succeeded",
        "generation_status": "succeeded",
        "provenance_code_git_sha": "c" * 40,
        "storage_ref": "s3://lumi-contract/generated/v1/result.png",
        "broker_message": {
            "job_id": str(task_id),
            "organization_id": str(organization_id),
            "project_id": str(project_id),
            "operation_id": str(operation_id),
            "trace_id": trace_id,
        },
        "evidence": {
            name: {"ref": f"fixture:{name}", "sha256": digest}
            for name in contract["required_evidence_stages"]
        },
    }
    fixture = {
        "release_candidate": {"git_sha": "c" * 40},
        "scenario_results": {
            "E2E-03": {
                "status": "PASS",
                "actual": "fixture completed",
                "evidence_ref": "fixture:e2e-03",
                "owner": "contract-test",
                "media_generation": observed,
            }
        },
    }
    validate_evidence(contract, fixture)

    drills: list[tuple[str, dict[str, Any]]] = []
    wrong_outbox = copy.deepcopy(fixture)
    wrong_outbox["scenario_results"]["E2E-03"]["media_generation"]["outbox_event_id"] = (
        "99999999-9999-4999-8999-999999999999"
    )
    drills.append(("wrong deterministic outbox id", wrong_outbox))

    wrong_broker = copy.deepcopy(fixture)
    wrong_broker["scenario_results"]["E2E-03"]["media_generation"]["broker_message"][
        "operation_id"
    ] = "99999999-9999-4999-8999-999999999999"
    drills.append(("broker operation mismatch", wrong_broker))

    wrong_sha = copy.deepcopy(fixture)
    wrong_sha["scenario_results"]["E2E-03"]["media_generation"]["provenance_code_git_sha"] = "d" * 40
    drills.append(("provenance rc sha mismatch", wrong_sha))

    missing_stage = copy.deepcopy(fixture)
    del missing_stage["scenario_results"]["E2E-03"]["media_generation"]["evidence"]["worker_execution"]
    drills.append(("missing worker evidence", missing_stage))

    for label, candidate in drills:
        try:
            validate_evidence(contract, candidate)
        except EvidenceError:
            continue
        raise EvidenceError(f"self-test negative drill unexpectedly passed: {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate NODE-73.3 canonical media-generation E2E evidence")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--evidence")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    try:
        contract = load_json(Path(args.contract))
        if args.self_test:
            self_test(contract)
            print(json.dumps({"status": "PASS", "self_test": True, "scenario_id": "E2E-03"}, indent=2))
            return 0
        if not args.evidence:
            raise EvidenceError("--evidence is required unless --self-test is used")
        result = validate_evidence(contract, load_json(Path(args.evidence)))
    except (EvidenceError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
