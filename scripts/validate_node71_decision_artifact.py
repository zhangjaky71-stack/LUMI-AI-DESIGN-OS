#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class DecisionArtifactError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionArtifactError(f"unable to read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DecisionArtifactError(f"{path} must contain a JSON object")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _positive_run_id(value: object) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise DecisionArtifactError("workflow run id must be a positive decimal integer")
    text = str(value)
    if not text.isdecimal() or int(text) <= 0:
        raise DecisionArtifactError("workflow run id must be a positive decimal integer")
    return text


def _canonical_run_url(url: object, repository: str) -> tuple[str, str]:
    if not isinstance(url, str):
        raise DecisionArtifactError("workflow run URL is missing")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.query or parsed.fragment:
        raise DecisionArtifactError("workflow run URL must be canonical github.com HTTPS without query/fragment")
    parts = [part for part in parsed.path.split("/") if part]
    repo_parts = repository.split("/", 1)
    if len(repo_parts) != 2 or not all(repo_parts):
        raise DecisionArtifactError("expected repository must use owner/name")
    if len(parts) != 5 or parts[:2] != repo_parts or parts[2:4] != ["actions", "runs"]:
        raise DecisionArtifactError("workflow run URL repository/path mismatch")
    return url, _positive_run_id(parts[4])


def build_provenance(
    *,
    decision_path: Path,
    repository: str,
    workflow_run_id: str,
    workflow_run_url: str,
) -> dict[str, Any]:
    decision = _load_json(decision_path)
    if decision.get("schema_version") != 1:
        raise DecisionArtifactError("NODE-71 decision schema_version must be 1")
    if decision.get("passed") is not True:
        raise DecisionArtifactError("NODE-71 decision provenance can only be captured for passed=true decision")
    decision_id = decision.get("decision_id")
    release_candidate = decision.get("release_candidate")
    if not isinstance(decision_id, str) or not decision_id:
        raise DecisionArtifactError("NODE-71 decision_id is missing")
    if not isinstance(release_candidate, dict):
        raise DecisionArtifactError("NODE-71 decision release_candidate is missing")
    _, url_run_id = _canonical_run_url(workflow_run_url, repository)
    expected_run_id = _positive_run_id(workflow_run_id)
    if url_run_id != expected_run_id:
        raise DecisionArtifactError("workflow run URL id differs from workflow_run_id")
    return {
        "schema_version": 1,
        "kind": "LUMI_NODE71_DECISION_PROVENANCE_V1",
        "repository": repository,
        "workflow": "Staging Acceptance Gate",
        "workflow_run_id": expected_run_id,
        "workflow_run_url": workflow_run_url,
        "decision_file": "decision.json",
        "decision_sha256": _sha256(decision_path),
        "decision_id": decision_id,
        "release_candidate": copy.deepcopy(release_candidate),
    }


def validate_artifact(
    *,
    decision_path: Path,
    provenance_path: Path,
    expected_run_id: str,
    expected_repository: str,
) -> dict[str, Any]:
    decision = _load_json(decision_path)
    provenance = _load_json(provenance_path)
    if provenance.get("schema_version") != 1:
        raise DecisionArtifactError("NODE-71 decision provenance schema_version must be 1")
    if provenance.get("kind") != "LUMI_NODE71_DECISION_PROVENANCE_V1":
        raise DecisionArtifactError("NODE-71 decision provenance kind mismatch")
    if provenance.get("repository") != expected_repository:
        raise DecisionArtifactError("NODE-71 decision provenance repository mismatch")
    if provenance.get("workflow") != "Staging Acceptance Gate":
        raise DecisionArtifactError("NODE-71 decision provenance workflow mismatch")
    run_id = _positive_run_id(provenance.get("workflow_run_id"))
    if run_id != _positive_run_id(expected_run_id):
        raise DecisionArtifactError("NODE-71 decision provenance run id mismatch")
    _, url_run_id = _canonical_run_url(provenance.get("workflow_run_url"), expected_repository)
    if url_run_id != run_id:
        raise DecisionArtifactError("NODE-71 decision provenance run URL id mismatch")
    if provenance.get("decision_file") != "decision.json":
        raise DecisionArtifactError("NODE-71 decision provenance file identity mismatch")
    if provenance.get("decision_sha256") != _sha256(decision_path):
        raise DecisionArtifactError("NODE-71 decision SHA-256 does not match provenance")
    if decision.get("schema_version") != 1 or decision.get("passed") is not True:
        raise DecisionArtifactError("NODE-71 downloaded decision is not a passed schema-v1 decision")
    if provenance.get("decision_id") != decision.get("decision_id"):
        raise DecisionArtifactError("NODE-71 decision_id differs from provenance")
    if provenance.get("release_candidate") != decision.get("release_candidate"):
        raise DecisionArtifactError("NODE-71 release_candidate differs from provenance")
    return {
        "status": "PASS",
        "workflow_run_id": run_id,
        "workflow_run_url": provenance.get("workflow_run_url"),
        "decision_id": decision.get("decision_id"),
        "decision_sha256": provenance.get("decision_sha256"),
        "release_candidate": decision.get("release_candidate"),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def self_test() -> dict[str, Any]:
    import tempfile

    repository = "example/lumi"
    run_id = "123"
    run_url = "https://github.com/example/lumi/actions/runs/123"
    with tempfile.TemporaryDirectory(prefix="lumi-node71-decision-") as temp_dir:
        root = Path(temp_dir)
        decision_path = root / "decision.json"
        provenance_path = root / "decision-provenance.json"
        decision = {
            "schema_version": 1,
            "decision_id": "node71-contract-001",
            "passed": True,
            "release_candidate": {
                "git_sha": "a" * 40,
                "version": "1.0.0-rc.contract",
                "migration_head": "contract-head",
            },
            "container_image_set": {"images": {}, "provenance": {}},
        }
        _write_json(decision_path, decision)
        provenance = build_provenance(
            decision_path=decision_path,
            repository=repository,
            workflow_run_id=run_id,
            workflow_run_url=run_url,
        )
        _write_json(provenance_path, provenance)
        clean = validate_artifact(
            decision_path=decision_path,
            provenance_path=provenance_path,
            expected_run_id=run_id,
            expected_repository=repository,
        )

        drills: list[str] = []

        def must_block(label: str, fn: object) -> None:
            try:
                fn()  # type: ignore[operator]
            except DecisionArtifactError:
                drills.append(label)
                return
            raise DecisionArtifactError(f"negative drill did not block: {label}")

        must_block(
            "requested_run_id_swap_blocked",
            lambda: validate_artifact(
                decision_path=decision_path,
                provenance_path=provenance_path,
                expected_run_id="999",
                expected_repository=repository,
            ),
        )
        must_block(
            "repository_swap_blocked",
            lambda: validate_artifact(
                decision_path=decision_path,
                provenance_path=provenance_path,
                expected_run_id=run_id,
                expected_repository="other/repo",
            ),
        )

        modified = copy.deepcopy(decision)
        modified["decision_id"] = "different"
        _write_json(decision_path, modified)
        must_block(
            "decision_content_swap_blocked",
            lambda: validate_artifact(
                decision_path=decision_path,
                provenance_path=provenance_path,
                expected_run_id=run_id,
                expected_repository=repository,
            ),
        )
        _write_json(decision_path, decision)

        bad_provenance = copy.deepcopy(provenance)
        bad_provenance["workflow_run_url"] = "https://github.com/example/lumi/actions/runs/999"
        _write_json(provenance_path, bad_provenance)
        must_block(
            "run_url_swap_blocked",
            lambda: validate_artifact(
                decision_path=decision_path,
                provenance_path=provenance_path,
                expected_run_id=run_id,
                expected_repository=repository,
            ),
        )

    return {"status": "PASS", "clean": clean, "negative_drills": drills}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate NODE-71 decision artifact workflow provenance")
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--expected-run-id")
    parser.add_argument("--expected-repository")
    parser.add_argument("--write-provenance", type=Path)
    parser.add_argument("--workflow-run-url")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0

    if args.write_provenance is not None:
        if args.decision is None or args.expected_run_id is None or args.expected_repository is None or args.workflow_run_url is None:
            raise DecisionArtifactError(
                "--decision, --expected-run-id, --expected-repository and --workflow-run-url are required to write provenance"
            )
        payload = build_provenance(
            decision_path=args.decision,
            repository=args.expected_repository,
            workflow_run_id=args.expected_run_id,
            workflow_run_url=args.workflow_run_url,
        )
        args.write_provenance.parent.mkdir(parents=True, exist_ok=True)
        _write_json(args.write_provenance, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.decision is None or args.provenance is None or args.expected_run_id is None or args.expected_repository is None:
        raise DecisionArtifactError(
            "--decision, --provenance, --expected-run-id and --expected-repository are required"
        )
    result = validate_artifact(
        decision_path=args.decision,
        provenance_path=args.provenance,
        expected_run_id=args.expected_run_id,
        expected_repository=args.expected_repository,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DecisionArtifactError as exc:
        raise SystemExit(f"NODE-71 decision artifact invalid: {exc}") from exc
