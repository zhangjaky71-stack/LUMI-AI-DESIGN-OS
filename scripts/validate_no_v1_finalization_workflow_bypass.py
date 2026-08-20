#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
CANONICAL_FINAL_CHECK = "node73-final-contract-gate"
FORBIDDEN_EXECUTABLES = (
    "scripts/final-acceptance-assembler.py",
    "scripts/validate_final_acceptance_package.py",
    "scripts/final-acceptance-decision.py",
)
REQUIRED_V2_WORKFLOWS = {
    ".github/workflows/assemble-final-acceptance.yml": (
        "scripts/final-acceptance-assembler-v2.py",
        "scripts/validate_final_acceptance_package_v2.py",
        "release-manifest-v2.json",
    ),
    ".github/workflows/final-acceptance-gate.yml": (
        "scripts/validate_final_acceptance_package_v2.py",
        "scripts/final-acceptance-decision-v2.py",
        "release-manifest-v2.json",
    ),
}


class V1FinalizationBypassError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise V1FinalizationBypassError(message)


def workflow_files() -> list[Path]:
    return sorted(
        path
        for suffix in ("*.yml", "*.yaml")
        for path in WORKFLOW_ROOT.glob(suffix)
        if path.is_file()
    )


def executable_occurrences(source: str, target: str) -> int:
    count = 0
    for line in source.splitlines():
        stripped = line.strip()
        if target not in stripped:
            continue
        if stripped.startswith("#"):
            continue
        count += 1
    return count


def validate_sources(sources: dict[str, str]) -> dict[str, Any]:
    require(bool(sources), "no GitHub workflows found")
    violations: list[str] = []
    for relative, source in sources.items():
        for target in FORBIDDEN_EXECUTABLES:
            if executable_occurrences(source, target):
                violations.append(f"{relative} invokes forbidden V1 finalization executable {target}")
    require(not violations, "; ".join(violations))

    for relative, markers in REQUIRED_V2_WORKFLOWS.items():
        source = sources.get(relative)
        require(isinstance(source, str), f"canonical V2 workflow missing: {relative}")
        for marker in markers:
            require(marker in source, f"canonical V2 workflow {relative} missing marker: {marker}")

    check_locations: list[str] = []
    for relative, source in sources.items():
        for line in source.splitlines():
            if line.strip() == f"name: {CANONICAL_FINAL_CHECK}":
                check_locations.append(relative)
    require(
        check_locations == [".github/workflows/final-acceptance-gate.yml"],
        f"canonical final required-check name must appear exactly once across workflows; found {check_locations}",
    )
    return {
        "status": "PASS",
        "workflow_count": len(sources),
        "forbidden_v1_executables": list(FORBIDDEN_EXECUTABLES),
        "canonical_final_check": CANONICAL_FINAL_CHECK,
        "canonical_final_check_workflow": check_locations[0],
    }


def load_repository_sources() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in workflow_files()
    }


def self_test() -> dict[str, Any]:
    clean = {
        ".github/workflows/assemble-final-acceptance.yml": (
            "run: python3 scripts/final-acceptance-assembler-v2.py\n"
            "run: python3 scripts/validate_final_acceptance_package_v2.py\n"
            "release-manifest-v2.json\n"
        ),
        ".github/workflows/final-acceptance-gate.yml": (
            "run: python3 scripts/validate_final_acceptance_package_v2.py\n"
            "run: python3 scripts/final-acceptance-decision-v2.py\n"
            "release-manifest-v2.json\n"
            f"name: {CANONICAL_FINAL_CHECK}\n"
        ),
        ".github/workflows/other.yml": "run: echo safe\n",
    }
    result = validate_sources(clean)
    blocked = 0
    drills: list[dict[str, str]] = []
    for target in FORBIDDEN_EXECUTABLES:
        mutated = dict(clean)
        mutated[".github/workflows/other.yml"] = f"run: python3 {target}\n"
        drills.append(mutated)
    duplicate = dict(clean)
    duplicate[".github/workflows/other.yml"] = f"name: {CANONICAL_FINAL_CHECK}\n"
    drills.append(duplicate)
    missing_v2 = dict(clean)
    missing_v2[".github/workflows/final-acceptance-gate.yml"] = f"name: {CANONICAL_FINAL_CHECK}\n"
    drills.append(missing_v2)

    for index, candidate in enumerate(drills, start=1):
        try:
            validate_sources(candidate)
        except V1FinalizationBypassError:
            blocked += 1
            continue
        raise V1FinalizationBypassError(f"negative workflow bypass drill did not block: {index}")
    return {"status": "PASS", "clean": result, "negative_drills": blocked}


def main() -> int:
    result = validate_sources(load_repository_sources())
    result["negative_drills"] = self_test()["negative_drills"]
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (V1FinalizationBypassError, OSError) as exc:
        raise SystemExit(f"V1 finalization workflow bypass contract failed: {exc}") from exc
