#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)  # noqa: S603
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def canonical_path(value: str, *, root: Path, expected_name: str | None = None) -> Path:
    candidate = (ROOT / value).resolve()
    allowed = root.resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise SystemExit(f"final acceptance path escapes {allowed.relative_to(ROOT)}/") from exc
    if expected_name is not None and candidate.name != expected_name:
        raise SystemExit(f"expected {expected_name}, got {candidate.name}")
    if not candidate.is_file():
        raise SystemExit(f"final acceptance file is missing: {value}")
    return candidate


def load_object(path: Path) -> dict[str, Any]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path.relative_to(ROOT)} is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{path.relative_to(ROOT)} must be a JSON object")
    return payload


def rc_identity(payload: dict[str, Any]) -> tuple[str, str, str]:
    candidate = payload.get("release_candidate")
    if not isinstance(candidate, dict):
        raise SystemExit("release_candidate is missing")
    sha = candidate.get("git_sha")
    version = candidate.get("version")
    migration = candidate.get("migration_head")
    if not isinstance(sha, str) or not SHA40.fullmatch(sha.lower()):
        raise SystemExit("release_candidate.git_sha must be an exact SHA40")
    if not isinstance(version, str) or not version.strip():
        raise SystemExit("release_candidate.version is missing")
    if not isinstance(migration, str) or not migration.strip():
        raise SystemExit("release_candidate.migration_head is missing")
    return sha.lower(), version, migration


def release_manifest(release_arg: str) -> dict[str, Any]:
    path = canonical_path(
        release_arg,
        root=ROOT / "reports" / "final-acceptance",
        expected_name="release-manifest.json",
    )
    return load_object(path)


def current_git_sha() -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit("unable to resolve current git HEAD for final acceptance")
    value = completed.stdout.strip().lower()
    if not SHA40.fullmatch(value):
        raise SystemExit(f"current git HEAD is not an exact SHA40: {value!r}")
    return value


def require_current_checkout_binding(release_arg: str) -> str:
    declared = rc_identity(release_manifest(release_arg))[0]
    actual = current_git_sha()
    if declared != actual:
        raise SystemExit(
            "FINAL_ACCEPTANCE_CHECKOUT_SHA_MISMATCH: "
            f"release manifest declares {declared}, current checkout is {actual}"
        )
    return actual


def require_all_upstream_rc_binding(release_arg: str, matrix_arg: str) -> tuple[str, ...]:
    release = release_manifest(release_arg)
    expected = rc_identity(release)
    matrix_path = canonical_path(
        matrix_arg,
        root=ROOT / "final" / "acceptance",
        expected_name="manifest-v1.json",
    )
    matrix = load_object(matrix_path)
    required = matrix.get("required_upstream_gates")
    if not isinstance(required, list) or not required or not all(
        isinstance(item, str) and item for item in required
    ):
        raise SystemExit("final acceptance matrix required_upstream_gates is invalid")
    if len(set(required)) != len(required):
        raise SystemExit("final acceptance matrix has duplicate required_upstream_gates")

    upstream = release.get("upstream_gates")
    if not isinstance(upstream, dict) or set(upstream) != set(required):
        raise SystemExit("release manifest upstream_gates do not match required upstream gates")

    bound: list[str] = []
    for name in required:
        spec = upstream.get(name)
        if not isinstance(spec, dict):
            raise SystemExit(f"upstream gate {name} freeze spec is missing")
        path_value = spec.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise SystemExit(f"upstream gate {name} path is missing")
        decision_path = canonical_path(path_value, root=ROOT / "reports")
        actual = rc_identity(load_object(decision_path))
        if actual != expected:
            raise SystemExit(
                "FINAL_ACCEPTANCE_UPSTREAM_RC_MISMATCH: "
                f"{name} expected {expected}, got {actual}"
            )
        bound.append(name)
    return tuple(bound)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Canonical NODE-73 final acceptance runner. "
            "Structured manual evidence is mandatory before the final product decision."
        )
    )
    parser.add_argument("--matrix", default="final/acceptance/manifest-v1.json")
    parser.add_argument("--release", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--manual-output", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    bound_sha = require_current_checkout_binding(args.release)
    upstream = require_all_upstream_rc_binding(args.release, args.matrix)
    print(
        json.dumps(
            {
                "final_acceptance_checkout_sha": bound_sha,
                "upstream_rc_bound": list(upstream),
            },
            sort_keys=True,
        )
    )

    run(
        [
            sys.executable,
            "scripts/final-manual-evidence-gate.py",
            "--release",
            args.release,
            "--evidence",
            args.evidence,
            "--output",
            args.manual_output,
        ]
    )
    run(
        [
            sys.executable,
            "scripts/final-acceptance-gate.py",
            "--matrix",
            args.matrix,
            "--release",
            args.release,
            "--evidence",
            args.evidence,
            "--output",
            args.output,
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
