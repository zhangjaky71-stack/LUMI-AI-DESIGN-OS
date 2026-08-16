#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run-final-acceptance.py"
RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lumi_final_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise SystemExit("unable to load canonical final acceptance runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo_output(release_id: str, value: str | None) -> Path:
    root = (ROOT / "reports" / "final-acceptance").resolve()
    path = (
        (ROOT / value).resolve()
        if value is not None
        else (root / release_id / "acceptance-evidence.json").resolve()
    )
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise SystemExit("output must stay under reports/final-acceptance/") from exc
    if path.name != "acceptance-evidence.json":
        raise SystemExit("output filename must be acceptance-evidence.json")
    if len(relative.parts) < 2 or relative.parts[0] != release_id:
        raise SystemExit("output must be under reports/final-acceptance/<release-id>/")
    return path


def assert_expected(label: str, expected: str | None, actual: str) -> None:
    if expected is not None and expected.strip() != actual:
        raise SystemExit(
            f"{label} assertion mismatch: expected {expected.strip()!r}, repository is {actual!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a fail-closed NODE-73 final acceptance evidence skeleton bound to the "
            "current repository Git SHA, VERSION and unique Alembic head."
        )
    )
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--output")
    parser.add_argument(
        "--git-sha",
        help="optional assertion only; must equal current git HEAD",
    )
    parser.add_argument(
        "--version",
        help="optional assertion only; must equal the root VERSION file",
    )
    parser.add_argument(
        "--migration-head",
        help="optional assertion only; must equal the repository's unique Alembic head",
    )
    args = parser.parse_args()

    release_id = args.release_id.strip()
    if not RELEASE_ID.fullmatch(release_id) or release_id.upper() == "PENDING":
        raise SystemExit(
            "release-id must use 1-128 safe characters: letters, digits, dot, underscore or dash"
        )

    runner = load_runner()
    git_sha, version, migration_head = runner.repository_release_identity()
    assert_expected("git-sha", args.git_sha, git_sha)
    assert_expected("version", args.version, version)
    assert_expected("migration-head", args.migration_head, migration_head)

    matrix = json.loads(
        (ROOT / "final" / "acceptance" / "manifest-v1.json").read_text(encoding="utf-8")
    )
    scenarios = matrix.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise SystemExit("final acceptance matrix scenarios are missing")
    ids = [scenario.get("id") for scenario in scenarios if isinstance(scenario, dict)]
    if len(ids) != len(scenarios) or any(not isinstance(item, str) or not item for item in ids):
        raise SystemExit("final acceptance matrix contains invalid scenario IDs")
    if len(set(ids)) != len(ids):
        raise SystemExit("final acceptance matrix contains duplicate scenario IDs")

    items = [
        {
            "id": scenario_id,
            "status": "NOT_RUN",
            "evidence_refs": [],
            "notes": "",
        }
        for scenario_id in ids
    ]
    payload = {
        "schema_version": 1,
        "release_id": release_id,
        "release_candidate": {
            "git_sha": git_sha,
            "version": version,
            "migration_head": migration_head,
        },
        "items": items,
    }

    output = repo_output(release_id, args.output)
    if output.exists():
        raise SystemExit(
            f"refusing to overwrite existing acceptance evidence: {output.relative_to(ROOT)}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "created": output.relative_to(ROOT).as_posix(),
                "release_id": release_id,
                "release_candidate": payload["release_candidate"],
                "scenario_count": len(items),
                "initial_status": "NOT_RUN",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
