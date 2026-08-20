#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DB_VALIDATOR = ROOT / "scripts" / "validate_staging_database_parity_evidence.py"
ARTIFACT_VALIDATOR = ROOT / "scripts" / "validate_staging_evidence_artifacts.py"
ARTIFACT_KIND = "LUMI_STAGING_EVIDENCE_ARTIFACT_V1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
TARGET_PARITY_IDS = ("PARITY-DB", "PARITY-MIGRATIONS")


class MergeError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MergeError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MergeError(f"unable to read {label}: {path}") from exc
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def staging_rc_sha(staging: Mapping[str, Any]) -> str:
    rc = staging.get("release_candidate")
    require(isinstance(rc, Mapping), "staging release_candidate is missing")
    value = rc.get("git_sha")
    require(isinstance(value, str) and bool(SHA40.fullmatch(value.lower())), "staging RC SHA must be exact SHA40")
    return value.lower()


def validate_frozen_inputs(
    staging: Mapping[str, Any],
    wrapper: Mapping[str, Any],
    catalog: Mapping[str, Any],
    *,
    wrapper_path: Path,
) -> tuple[str, str]:
    rc_sha = staging_rc_sha(staging)
    artifact_id = f"staging-database-parity:{rc_sha}"
    require(wrapper.get("schema_version") == 1, "database parity wrapper schema_version must be 1")
    require(wrapper.get("kind") == ARTIFACT_KIND, "database parity wrapper kind mismatch")
    require(wrapper.get("artifact_id") == artifact_id, "database parity wrapper artifact_id mismatch")
    require(wrapper.get("status") == "PASS", "database parity wrapper must PASS")
    require(wrapper.get("rc_git_sha") == rc_sha, "database parity wrapper RC SHA mismatch")

    payload = wrapper.get("payload")
    require(isinstance(payload, Mapping), "database parity wrapper payload is missing")
    raw = payload.get("raw_evidence")
    validation = payload.get("validation")
    require(isinstance(raw, Mapping), "database parity wrapper raw_evidence is missing")
    require(isinstance(validation, Mapping), "database parity wrapper validation is missing")
    db_validator = load_module(DB_VALIDATOR, "lumi_staging_db_parity_evidence")
    recomputed = db_validator.validate(raw, expected_git_sha=rc_sha)
    require(dict(validation) == recomputed, "database parity wrapper validation differs from recomputation")

    require(set(catalog) == {artifact_id}, "database parity catalog must contain exactly its canonical artifact id")
    entry = catalog.get(artifact_id)
    require(isinstance(entry, Mapping), "database parity catalog entry is missing")
    require(entry.get("rc_git_sha") == rc_sha, "database parity catalog RC SHA mismatch")
    expected_path = f"reports/staging-acceptance/evidence/{rc_sha}/database-parity.json"
    require(entry.get("path") == expected_path, "database parity catalog path is not canonical")
    require(wrapper_path.as_posix().endswith(expected_path), "database parity wrapper input path does not match canonical catalog path")
    require(entry.get("sha256") == sha256(wrapper_path), "database parity catalog SHA-256 differs from wrapper bytes")
    return rc_sha, artifact_id


def _forbid_scenario_use(staging: Mapping[str, Any], artifact_id: str) -> None:
    scenarios = staging.get("scenario_results", {})
    require(isinstance(scenarios, Mapping), "staging scenario_results must be an object")
    for scenario_id, raw in scenarios.items():
        if isinstance(raw, Mapping) and raw.get("evidence_ref") == artifact_id:
            raise MergeError(
                f"database parity artifact is parity-only and cannot evidence scenario_results.{scenario_id}"
            )


def merge(
    staging: dict[str, Any],
    wrapper: dict[str, Any],
    catalog: dict[str, Any],
    *,
    wrapper_path: Path,
    validation_root: Path = ROOT,
) -> dict[str, Any]:
    rc_sha, artifact_id = validate_frozen_inputs(staging, wrapper, catalog, wrapper_path=wrapper_path)
    _forbid_scenario_use(staging, artifact_id)
    before_scenarios = copy.deepcopy(staging.get("scenario_results", {}))
    parity = staging.get("environment_parity")
    require(isinstance(parity, dict), "staging environment_parity must be an object")
    for parity_id in TARGET_PARITY_IDS:
        require(parity_id not in parity, f"refusing to overwrite existing environment parity result: {parity_id}")

    artifacts = staging.get("evidence_artifacts")
    require(isinstance(artifacts, dict), "staging evidence_artifacts must be an object")
    require(artifact_id not in artifacts, "refusing to overwrite existing database parity artifact catalog entry")

    merged = copy.deepcopy(staging)
    merged["environment_parity"]["PARITY-DB"] = {
        "status": "PASS",
        "evidence_ref": artifact_id,
    }
    merged["environment_parity"]["PARITY-MIGRATIONS"] = {
        "status": "PASS",
        "evidence_ref": artifact_id,
    }
    merged["evidence_artifacts"][artifact_id] = copy.deepcopy(catalog[artifact_id])
    require(merged.get("scenario_results", {}) == before_scenarios, "database parity merge must not mutate scenario_results")

    artifact_validator = load_module(ARTIFACT_VALIDATOR, "lumi_staging_evidence_artifacts")
    result = artifact_validator.validate_evidence(merged, root=validation_root)
    require(result.get("status") == "PASS", "merged staging evidence failed generic artifact binding")
    require(result.get("rc_git_sha") == rc_sha, "merged artifact binding RC SHA mismatch")
    return merged


def self_test() -> dict[str, Any]:
    rc_sha = "a" * 40
    artifact_id = f"staging-database-parity:{rc_sha}"
    db_validator = load_module(DB_VALIDATOR, "lumi_staging_db_parity_fixture")
    raw = db_validator.fixture()
    raw["release_candidate"]["git_sha"] = rc_sha
    validation = db_validator.validate(raw, expected_git_sha=rc_sha)

    with tempfile.TemporaryDirectory(prefix="lumi-db-parity-merge-") as temp_raw:
        root = Path(temp_raw)
        artifact_dir = root / "reports" / "staging-acceptance" / "evidence" / rc_sha
        artifact_dir.mkdir(parents=True)
        wrapper_path = artifact_dir / "database-parity.json"
        wrapper = {
            "schema_version": 1,
            "kind": ARTIFACT_KIND,
            "artifact_id": artifact_id,
            "status": "PASS",
            "rc_git_sha": rc_sha,
            "captured_at": "2026-08-20T00:00:00Z",
            "producer": {
                "repository": "zhangjaky71-stack/LUMI-AI-DESIGN-OS",
                "workflow": "Collect Staging Database Parity",
                "workflow_path": ".github/workflows/collect-staging-database-parity.yml",
                "run_id": 123,
                "run_attempt": 1,
                "run_url": "https://github.com/zhangjaky71-stack/LUMI-AI-DESIGN-OS/actions/runs/123",
                "head_sha": "b" * 40,
                "head_branch": "release-closure-p0",
            },
            "payload": {
                "validation": validation,
                "raw_evidence_sha256": "c" * 64,
                "raw_evidence": raw,
            },
        }
        wrapper_path.write_text(json.dumps(wrapper, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        catalog = {
            artifact_id: {
                "path": f"reports/staging-acceptance/evidence/{rc_sha}/database-parity.json",
                "sha256": sha256(wrapper_path),
                "rc_git_sha": rc_sha,
            }
        }
        staging = {
            "release_candidate": {"git_sha": rc_sha},
            "environment_parity": {},
            "scenario_results": {"ENV-02": {"status": "NOT_RUN"}},
            "evidence_artifacts": {},
        }
        clean = merge(staging, wrapper, catalog, wrapper_path=wrapper_path, validation_root=root)
        require(clean["environment_parity"]["PARITY-DB"]["status"] == "PASS", "clean PARITY-DB merge failed")
        require(clean["environment_parity"]["PARITY-MIGRATIONS"]["status"] == "PASS", "clean PARITY-MIGRATIONS merge failed")
        require(clean["scenario_results"] == staging["scenario_results"], "clean merge changed scenarios")

        blocked = 0
        mutations: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]] = []
        overwrite = copy.deepcopy(staging)
        overwrite["environment_parity"]["PARITY-DB"] = {"status": "FAIL", "evidence_ref": "old"}
        mutations.append((overwrite, wrapper, catalog, wrapper_path))
        scenario_attempt = copy.deepcopy(staging)
        scenario_attempt["scenario_results"]["ENV-02"] = {"status": "PASS", "evidence_ref": artifact_id}
        mutations.append((scenario_attempt, wrapper, catalog, wrapper_path))
        bad_rc = copy.deepcopy(wrapper)
        bad_rc["rc_git_sha"] = "d" * 40
        mutations.append((staging, bad_rc, catalog, wrapper_path))
        bad_validation = copy.deepcopy(wrapper)
        bad_validation["payload"]["validation"]["postgres_major"] = 15
        mutations.append((staging, bad_validation, catalog, wrapper_path))
        bad_catalog = copy.deepcopy(catalog)
        bad_catalog[artifact_id]["sha256"] = "e" * 64
        mutations.append((staging, wrapper, bad_catalog, wrapper_path))

        for index, (stage, wrap, cat, path) in enumerate(mutations, start=1):
            try:
                merge(stage, wrap, cat, wrapper_path=path, validation_root=root)
            except Exception:
                blocked += 1
                continue
            raise MergeError(f"negative DB parity merge drill did not block: {index}")

        return {"status": "PASS", "negative_drills": blocked, "scenario_results_unchanged": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge frozen database parity wrapper into NODE-71 staging evidence")
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--wrapper", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            result = self_test()
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        require(all(value is not None for value in (args.staging, args.wrapper, args.catalog, args.output)), "--staging/--wrapper/--catalog/--output are required")
        assert args.staging is not None and args.wrapper is not None and args.catalog is not None and args.output is not None
        output = args.output.resolve()
        require(output not in {args.staging.resolve(), args.wrapper.resolve(), args.catalog.resolve()}, "output must not overwrite an input")
        merged = merge(
            load(args.staging, "staging evidence"),
            load(args.wrapper, "database parity wrapper"),
            load(args.catalog, "database parity catalog"),
            wrapper_path=args.wrapper.resolve(),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(output)
        return 0
    except (MergeError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"staging database parity merge blocked: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
