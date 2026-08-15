#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def repo_output(value: str) -> Path:
    path = (ROOT / value).resolve()
    root = (ROOT / "reports" / "final-acceptance").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SystemExit("output must stay under reports/final-acceptance/") from exc
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a fail-closed NODE-73 final acceptance evidence skeleton")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--migration-head", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not args.release_id.strip() or args.release_id.upper() == "PENDING":
        raise SystemExit("release-id must be concrete")
    if not SHA40.fullmatch(args.git_sha.lower()):
        raise SystemExit("git-sha must be exact SHA40")
    if not args.version.strip() or not args.migration_head.strip():
        raise SystemExit("version and migration-head are required")

    matrix = json.loads((ROOT / "final" / "acceptance" / "manifest-v1.json").read_text(encoding="utf-8"))
    items = []
    for scenario in matrix["scenarios"]:
        items.append({
            "id": scenario["id"],
            "status": "NOT_RUN",
            "evidence_refs": [],
            "notes": "",
        })

    payload = {
        "schema_version": 1,
        "release_id": args.release_id,
        "release_candidate": {
            "git_sha": args.git_sha.lower(),
            "version": args.version,
            "migration_head": args.migration_head,
        },
        "items": items,
    }
    output = repo_output(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"created {output.relative_to(ROOT)} with {len(items)} NOT_RUN scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
