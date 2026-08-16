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


def load_release_candidate_sha(release_arg: str) -> str:
    release_path = (ROOT / release_arg).resolve()
    allowed = (ROOT / "reports" / "final-acceptance").resolve()
    try:
        release_path.relative_to(allowed)
    except ValueError as exc:
        raise SystemExit("release manifest escapes reports/final-acceptance/") from exc
    if release_path.name != "release-manifest.json" or not release_path.is_file():
        raise SystemExit("expected an existing reports/final-acceptance/<release>/release-manifest.json")
    try:
        payload: Any = json.loads(release_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"release manifest is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("release manifest must be a JSON object")
    candidate = payload.get("release_candidate")
    if not isinstance(candidate, dict):
        raise SystemExit("release manifest release_candidate is missing")
    value = candidate.get("git_sha")
    if not isinstance(value, str) or not SHA40.fullmatch(value.lower()):
        raise SystemExit("release_candidate.git_sha must be an exact SHA40")
    return value.lower()


def require_current_checkout_binding(release_arg: str) -> str:
    declared = load_release_candidate_sha(release_arg)
    actual = current_git_sha()
    if declared != actual:
        raise SystemExit(
            "FINAL_ACCEPTANCE_CHECKOUT_SHA_MISMATCH: "
            f"release manifest declares {declared}, current checkout is {actual}"
        )
    return actual


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
    print(json.dumps({"final_acceptance_checkout_sha": bound_sha}, sort_keys=True))

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
