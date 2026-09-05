#!/usr/bin/env python3
from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROOT_PYPROJECT = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"


class LockCoverageError(RuntimeError):
    pass


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    if not isinstance(raw, dict):
        raise LockCoverageError(f"{path.relative_to(ROOT)} must contain a TOML table")
    return raw


def _project_name(pyproject: Path) -> str:
    raw = _load_toml(pyproject)
    project = raw.get("project")
    if not isinstance(project, dict):
        raise LockCoverageError(f"{pyproject.relative_to(ROOT)} is missing [project]")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        raise LockCoverageError(f"{pyproject.relative_to(ROOT)} project.name is missing")
    return name.strip()


def expected_workspace_packages() -> dict[str, str]:
    root = _load_toml(ROOT_PYPROJECT)
    tool = root.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    workspace = uv.get("workspace") if isinstance(uv, dict) else None
    members = workspace.get("members") if isinstance(workspace, dict) else None
    if not isinstance(members, list) or not members or not all(isinstance(item, str) for item in members):
        raise LockCoverageError("pyproject.toml [tool.uv.workspace].members must be a non-empty string array")

    expected: dict[str, str] = {_project_name(ROOT_PYPROJECT): "."}
    for relative in members:
        member_path = Path(relative)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise LockCoverageError(f"unsafe workspace member path: {relative}")
        pyproject = ROOT / member_path / "pyproject.toml"
        if not pyproject.is_file():
            raise LockCoverageError(f"workspace member has no pyproject.toml: {relative}")
        name = _project_name(pyproject)
        previous = expected.get(name)
        if previous is not None:
            raise LockCoverageError(
                f"duplicate workspace project name {name!r}: {previous} and {relative}"
            )
        expected[name] = member_path.as_posix().rstrip("/")
    return expected


def locked_workspace_members() -> set[str]:
    lock = _load_toml(UV_LOCK)
    manifest = lock.get("manifest")
    members = manifest.get("members") if isinstance(manifest, dict) else None
    if not isinstance(members, list) or not all(isinstance(item, str) for item in members):
        raise LockCoverageError("uv.lock [manifest].members must be a string array")
    if len(members) != len(set(members)):
        raise LockCoverageError("uv.lock [manifest].members contains duplicate package names")
    return set(members)


def evaluate() -> dict[str, Any]:
    expected = expected_workspace_packages()
    locked = locked_workspace_members()
    expected_names = set(expected)
    missing = sorted(expected_names - locked)
    unexpected = sorted(locked - expected_names)
    return {
        "status": "PASS" if not missing and not unexpected else "BLOCKED",
        "expected_count": len(expected_names),
        "locked_count": len(locked),
        "missing_workspace_packages": missing,
        "unexpected_locked_workspace_packages": unexpected,
        "workspace_packages": [
            {"name": name, "path": expected[name]} for name in sorted(expected)
        ],
    }


def main() -> int:
    try:
        result = evaluate()
    except (LockCoverageError, OSError, tomllib.TOMLDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
