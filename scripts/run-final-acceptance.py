#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE_ONLY_PREFIXES = ("reports/",)


def run(command: list[str]) -> None:
    completed = subprocess.run(command, cwd=ROOT, check=False)  # noqa: S603
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def git(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=capture,
        text=True,
    )


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
    return sha.lower(), version.strip(), migration.strip()


def release_manifest(release_arg: str) -> dict[str, Any]:
    path = canonical_path(
        release_arg,
        root=ROOT / "reports" / "final-acceptance",
        expected_name="release-manifest.json",
    )
    return load_object(path)


def current_git_sha() -> str:
    completed = git(["rev-parse", "HEAD"])
    if completed.returncode != 0:
        raise SystemExit("unable to resolve current git HEAD for final acceptance")
    value = completed.stdout.strip().lower()
    if not SHA40.fullmatch(value):
        raise SystemExit(f"current git HEAD is not an exact SHA40: {value!r}")
    return value


def current_version() -> str:
    path = ROOT / "VERSION"
    if not path.is_file():
        raise SystemExit("VERSION file is missing")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise SystemExit("VERSION file is empty")
    return value


def current_migration_head() -> str:
    revisions: dict[str, tuple[str, ...]] = {}
    root = ROOT / "apps" / "api" / "alembic" / "versions"
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        values: dict[str, Any] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name) or target.id not in {"revision", "down_revision"}:
                continue
            try:
                values[target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
        revision = values.get("revision")
        if not isinstance(revision, str) or not revision:
            continue
        raw_parent = values.get("down_revision")
        if raw_parent is None:
            parents: tuple[str, ...] = ()
        elif isinstance(raw_parent, str):
            parents = (raw_parent,)
        elif isinstance(raw_parent, (tuple, list)) and all(
            isinstance(item, str) for item in raw_parent
        ):
            parents = tuple(raw_parent)
        else:
            raise SystemExit(f"unsupported down_revision in {path.relative_to(ROOT)}")
        if revision in revisions:
            raise SystemExit(f"duplicate Alembic revision {revision}")
        revisions[revision] = parents

    if not revisions:
        raise SystemExit("no Alembic revisions found")
    referenced = {parent for parents in revisions.values() for parent in parents}
    unknown = sorted(referenced - set(revisions))
    if unknown:
        raise SystemExit(f"Alembic graph references unknown revisions: {unknown}")
    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        raise SystemExit(f"expected exactly one Alembic head, found {heads}")
    return heads[0]


def repository_release_identity() -> tuple[str, str, str]:
    """Identity to freeze when creating a new source release candidate."""
    return current_git_sha(), current_version(), current_migration_head()


def require_clean_worktree() -> None:
    completed = git(["status", "--porcelain", "--untracked-files=all"])
    if completed.returncode != 0:
        raise SystemExit("unable to inspect git worktree for final acceptance")
    dirty = [line for line in completed.stdout.splitlines() if line.strip()]
    if dirty:
        preview = "; ".join(dirty[:20])
        raise SystemExit(
            "FINAL_ACCEPTANCE_DIRTY_WORKTREE: canonical final acceptance requires a clean "
            f"checkout; dirty entries: {preview}"
        )


def evidence_only_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return any(normalized.startswith(prefix) for prefix in EVIDENCE_ONLY_PREFIXES)


def require_evidence_only_descendant(release_sha: str) -> tuple[str, tuple[str, ...]]:
    exists = git(["cat-file", "-e", f"{release_sha}^{{commit}}"])
    if exists.returncode != 0:
        raise SystemExit(f"release candidate commit does not exist locally: {release_sha}")

    ancestor = git(["merge-base", "--is-ancestor", release_sha, "HEAD"])
    if ancestor.returncode != 0:
        raise SystemExit(
            "FINAL_ACCEPTANCE_RC_NOT_ANCESTOR: release candidate is not an ancestor of "
            "the evidence checkout"
        )

    changed = git(["diff", "--name-only", f"{release_sha}..HEAD", "--"])
    if changed.returncode != 0:
        raise SystemExit("unable to inspect post-RC changes")
    paths = tuple(line.strip() for line in changed.stdout.splitlines() if line.strip())
    invalid = tuple(path for path in paths if not evidence_only_path(path))
    if invalid:
        raise SystemExit(
            "FINAL_ACCEPTANCE_POST_RC_SOURCE_CHANGE: only reports/ evidence commits are "
            f"allowed after source RC freeze; invalid paths={list(invalid)}"
        )
    return current_git_sha(), paths


def require_repository_identity_binding(
    release_arg: str,
) -> tuple[tuple[str, str, str], str, tuple[str, ...]]:
    declared = rc_identity(release_manifest(release_arg))
    current_source_facts = (current_version(), current_migration_head())
    if declared[1:] != current_source_facts:
        raise SystemExit(
            "FINAL_ACCEPTANCE_REPOSITORY_IDENTITY_MISMATCH: "
            f"release manifest declares version/head {declared[1:]}, "
            f"repository has {current_source_facts}"
        )
    evidence_checkout_sha, evidence_paths = require_evidence_only_descendant(declared[0])
    return declared, evidence_checkout_sha, evidence_paths


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

    require_clean_worktree()
    release_identity, evidence_checkout_sha, evidence_paths = require_repository_identity_binding(
        args.release
    )
    upstream = require_all_upstream_rc_binding(args.release, args.matrix)
    print(
        json.dumps(
            {
                "release_candidate": {
                    "git_sha": release_identity[0],
                    "version": release_identity[1],
                    "migration_head": release_identity[2],
                },
                "evidence_checkout_sha": evidence_checkout_sha,
                "post_rc_evidence_paths": list(evidence_paths),
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
