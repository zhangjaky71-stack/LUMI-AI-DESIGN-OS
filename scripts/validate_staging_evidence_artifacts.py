#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPOSITORY = "zhangjaky71-stack/LUMI-AI-DESIGN-OS"
ARTIFACT_KIND = "LUMI_STAGING_EVIDENCE_ARTIFACT_V1"
ALLOWED_ROOT = Path("reports/staging-acceptance/evidence")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_REF = re.compile(r"^[A-Za-z0-9._:-]+$")


class StagingEvidenceArtifactError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StagingEvidenceArtifactError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StagingEvidenceArtifactError(f"unable to read JSON {path}: {exc}") from exc
    require(isinstance(payload, dict), f"{path} must contain a JSON object")
    return payload


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def non_pending_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().upper() != "PENDING"


def normalize_rc_sha(evidence: Mapping[str, Any]) -> str:
    rc = evidence.get("release_candidate")
    require(isinstance(rc, Mapping), "release_candidate object is missing")
    value = rc.get("git_sha")
    require(isinstance(value, str) and bool(SHA40.fullmatch(value.lower())), "release_candidate.git_sha must be exact SHA40")
    return value.lower()


def _collect_pass_refs(container: object, *, label: str) -> dict[str, list[str]]:
    require(isinstance(container, Mapping), f"{label} must be an object")
    refs: dict[str, list[str]] = {}
    for item_id, raw in container.items():
        require(isinstance(item_id, str) and bool(item_id), f"{label} contains invalid id")
        if not isinstance(raw, Mapping) or raw.get("status") != "PASS":
            continue
        ref = raw.get("evidence_ref")
        require(non_pending_string(ref), f"PASS {label} {item_id} must include evidence_ref")
        ref_text = str(ref)
        require(bool(SAFE_REF.fullmatch(ref_text)), f"PASS {label} {item_id} evidence_ref has unsafe format")
        refs.setdefault(ref_text, []).append(f"{label}:{item_id}")
    return refs


def required_refs(evidence: Mapping[str, Any]) -> dict[str, list[str]]:
    refs = _collect_pass_refs(evidence.get("environment_parity", {}), label="environment_parity")
    for ref, origins in _collect_pass_refs(evidence.get("scenario_results", {}), label="scenario_results").items():
        refs.setdefault(ref, []).extend(origins)
    return {ref: sorted(origins) for ref, origins in sorted(refs.items())}


def validate_catalog_metadata(evidence: Mapping[str, Any]) -> dict[str, Any]:
    rc_sha = normalize_rc_sha(evidence)
    refs = required_refs(evidence)
    catalog = evidence.get("evidence_artifacts")
    require(isinstance(catalog, Mapping), "evidence_artifacts catalog is missing")

    normalized: dict[str, Any] = {}
    for ref, origins in refs.items():
        entry = catalog.get(ref)
        require(isinstance(entry, Mapping), f"evidence_ref {ref} is not present in evidence_artifacts")
        path = entry.get("path")
        expected_sha = entry.get("sha256")
        entry_rc = entry.get("rc_git_sha")
        require(non_pending_string(path), f"evidence_artifacts[{ref}].path is missing/PENDING")
        require(isinstance(expected_sha, str) and bool(SHA256.fullmatch(expected_sha.lower())), f"evidence_artifacts[{ref}].sha256 must be SHA-256")
        require(entry_rc == rc_sha, f"evidence_artifacts[{ref}].rc_git_sha must equal release_candidate.git_sha")
        normalized[ref] = {
            "path": str(path),
            "sha256": expected_sha.lower(),
            "rc_git_sha": rc_sha,
            "origins": origins,
        }
    return {
        "rc_git_sha": rc_sha,
        "required_ref_count": len(refs),
        "artifacts": normalized,
    }


def _safe_repo_path(root: Path, raw: str) -> Path:
    require("\\" not in raw, "evidence artifact path must use POSIX separators")
    candidate_lexical = root / raw
    allowed = (root / ALLOWED_ROOT).resolve()
    candidate = candidate_lexical.resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise StagingEvidenceArtifactError(f"evidence artifact path escapes {ALLOWED_ROOT.as_posix()}: {raw}") from exc

    current = candidate_lexical
    while current != root and root in current.parents:
        require(not current.is_symlink(), f"evidence artifact path contains symlink: {raw}")
        current = current.parent
    require(candidate.is_file(), f"evidence artifact file does not exist: {raw}")
    return candidate


def validate_artifact_payload(payload: Mapping[str, Any], *, ref: str, rc_sha: str) -> dict[str, Any]:
    require(payload.get("schema_version") == 1, f"artifact {ref} schema_version must be 1")
    require(payload.get("kind") == ARTIFACT_KIND, f"artifact {ref} kind mismatch")
    require(payload.get("artifact_id") == ref, f"artifact {ref} artifact_id mismatch")
    require(payload.get("status") == "PASS", f"artifact {ref} status must be PASS")
    require(payload.get("rc_git_sha") == rc_sha, f"artifact {ref} rc_git_sha mismatch")
    require(non_pending_string(payload.get("captured_at")), f"artifact {ref} captured_at is missing/PENDING")

    producer = payload.get("producer")
    require(isinstance(producer, Mapping), f"artifact {ref} producer object is missing")
    require(producer.get("repository") == EXPECTED_REPOSITORY, f"artifact {ref} producer repository mismatch")
    run_id = producer.get("run_id")
    run_text = str(run_id) if isinstance(run_id, (str, int)) and not isinstance(run_id, bool) else ""
    require(run_text.isdecimal() and int(run_text) > 0, f"artifact {ref} producer.run_id must be positive decimal")
    require(non_pending_string(producer.get("workflow")), f"artifact {ref} producer.workflow is missing/PENDING")
    run_url = producer.get("run_url")
    expected_url = f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/{run_text}"
    require(isinstance(run_url, str) and run_url == expected_url, f"artifact {ref} producer.run_url mismatch")
    return {
        "artifact_id": ref,
        "producer_run_id": run_text,
        "producer_workflow": str(producer["workflow"]),
        "captured_at": str(payload["captured_at"]),
    }


def validate_evidence(evidence: Mapping[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    metadata = validate_catalog_metadata(evidence)
    rc_sha = metadata["rc_git_sha"]
    verified: dict[str, Any] = {}
    for ref, entry in metadata["artifacts"].items():
        path = _safe_repo_path(root, entry["path"])
        actual_sha = digest(path)
        require(actual_sha == entry["sha256"], f"evidence artifact SHA-256 mismatch: {ref}")
        payload = load_json(path)
        artifact = validate_artifact_payload(payload, ref=ref, rc_sha=rc_sha)
        verified[ref] = {**entry, **artifact}
    return {
        "schema_version": 1,
        "kind": "LUMI_STAGING_EVIDENCE_ARTIFACT_BINDING_V1",
        "status": "PASS",
        "repository": EXPECTED_REPOSITORY,
        "rc_git_sha": rc_sha,
        "required_ref_count": metadata["required_ref_count"],
        "verified_artifact_count": len(verified),
        "verified_artifacts": verified,
    }


def _artifact_payload(ref: str, rc_sha: str, run_id: int, *, status: str = "PASS") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": ARTIFACT_KIND,
        "artifact_id": ref,
        "status": status,
        "rc_git_sha": rc_sha,
        "captured_at": "2026-08-20T00:00:00Z",
        "producer": {
            "repository": EXPECTED_REPOSITORY,
            "workflow": "self-test",
            "run_id": run_id,
            "run_url": f"https://github.com/{EXPECTED_REPOSITORY}/actions/runs/{run_id}",
        },
        "payload": {"summary": "self-test"},
    }


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="lumi-staging-artifacts-") as temp_raw:
        root = Path(temp_raw)
        artifact_root = root / ALLOWED_ROOT
        artifact_root.mkdir(parents=True)
        rc_sha = "a" * 40
        refs = ["artifact:parity:PARITY-DB", "artifact:scenario:ENV-02"]
        catalog: dict[str, Any] = {}
        for index, ref in enumerate(refs, start=101):
            path = artifact_root / f"artifact-{index}.json"
            path.write_text(json.dumps(_artifact_payload(ref, rc_sha, index), sort_keys=True), encoding="utf-8")
            catalog[ref] = {
                "path": path.relative_to(root).as_posix(),
                "sha256": digest(path),
                "rc_git_sha": rc_sha,
            }
        clean = {
            "release_candidate": {"git_sha": rc_sha},
            "environment_parity": {
                "PARITY-DB": {"status": "PASS", "evidence_ref": refs[0]},
            },
            "scenario_results": {
                "ENV-02": {"status": "PASS", "evidence_ref": refs[1]},
                "AI-01": {"status": "BLOCKED_EXTERNAL", "evidence_ref": "ticket:provider"},
            },
            "evidence_artifacts": catalog,
        }
        result = validate_evidence(clean, root=root)
        require(result["verified_artifact_count"] == 2, "clean artifact binding fixture did not verify two artifacts")

        blocked = 0
        mutations: list[dict[str, Any]] = []

        missing = json.loads(json.dumps(clean))
        missing["evidence_artifacts"].pop(refs[1])
        mutations.append(missing)

        bad_hash = json.loads(json.dumps(clean))
        bad_hash["evidence_artifacts"][refs[0]]["sha256"] = "b" * 64
        mutations.append(bad_hash)

        bad_rc = json.loads(json.dumps(clean))
        bad_rc["evidence_artifacts"][refs[0]]["rc_git_sha"] = "c" * 40
        mutations.append(bad_rc)

        escape = json.loads(json.dumps(clean))
        escape["evidence_artifacts"][refs[0]]["path"] = "outside.json"
        mutations.append(escape)

        bad_id_path = artifact_root / "bad-id.json"
        bad_id_path.write_text(json.dumps(_artifact_payload("artifact:wrong", rc_sha, 201), sort_keys=True), encoding="utf-8")
        bad_id = json.loads(json.dumps(clean))
        bad_id["evidence_artifacts"][refs[0]] = {
            "path": bad_id_path.relative_to(root).as_posix(),
            "sha256": digest(bad_id_path),
            "rc_git_sha": rc_sha,
        }
        mutations.append(bad_id)

        bad_status_path = artifact_root / "bad-status.json"
        bad_status_path.write_text(json.dumps(_artifact_payload(refs[0], rc_sha, 202, status="FAIL"), sort_keys=True), encoding="utf-8")
        bad_status = json.loads(json.dumps(clean))
        bad_status["evidence_artifacts"][refs[0]] = {
            "path": bad_status_path.relative_to(root).as_posix(),
            "sha256": digest(bad_status_path),
            "rc_git_sha": rc_sha,
        }
        mutations.append(bad_status)

        bad_producer_path = artifact_root / "bad-producer.json"
        bad_producer_payload = _artifact_payload(refs[0], rc_sha, 203)
        bad_producer_payload["producer"].pop("workflow")
        bad_producer_path.write_text(json.dumps(bad_producer_payload, sort_keys=True), encoding="utf-8")
        bad_producer = json.loads(json.dumps(clean))
        bad_producer["evidence_artifacts"][refs[0]] = {
            "path": bad_producer_path.relative_to(root).as_posix(),
            "sha256": digest(bad_producer_path),
            "rc_git_sha": rc_sha,
        }
        mutations.append(bad_producer)

        for index, mutation in enumerate(mutations, start=1):
            try:
                validate_evidence(mutation, root=root)
            except StagingEvidenceArtifactError:
                blocked += 1
                continue
            raise StagingEvidenceArtifactError(f"negative staging evidence artifact drill did not block: {index}")

        return {"status": "PASS", "negative_drills": blocked, "verified_artifacts": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate immutable NODE-71 Staging evidence artifact bindings")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            result = self_test()
        else:
            require(args.evidence is not None, "--evidence is required unless --self-test is used")
            evidence = load_json(args.evidence)
            result = validate_evidence(evidence, root=ROOT)
        encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            output = args.output.resolve()
            allowed = (ROOT / "reports" / "staging-acceptance" / "runtime").resolve()
            try:
                output.relative_to(allowed)
            except ValueError as exc:
                raise StagingEvidenceArtifactError("output must stay below reports/staging-acceptance/runtime/") from exc
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0
    except (StagingEvidenceArtifactError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"staging evidence artifact binding blocked: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
