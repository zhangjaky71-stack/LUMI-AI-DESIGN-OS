#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)  # noqa: S603
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


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
