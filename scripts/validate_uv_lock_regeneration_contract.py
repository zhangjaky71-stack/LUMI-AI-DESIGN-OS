#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "regenerate-uv-lock.yml"


class LockWorkflowContractError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LockWorkflowContractError(message)


def job_block(source: str, job: str, next_job: str | None) -> str:
    marker = f"  {job}:\n"
    start = source.find(marker)
    require(start >= 0, f"missing uv-lock workflow job: {job}")
    if next_job is None:
        return source[start:]
    end = source.find(f"  {next_job}:\n", start + len(marker))
    require(end >= 0, f"missing uv-lock workflow job terminator: {next_job}")
    return source[start:end]


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    header_end = text.find("jobs:\n")
    require(header_end >= 0, "canonical uv-lock workflow has no jobs section")
    header = text[:header_end]

    for marker in (
        "workflow_dispatch:",
        "expected_sha:",
        "confirm:",
        "permissions:\n  contents: read\n",
        "TARGET_REF: release-closure-p0",
        "REGENERATE_NODE73_UV_LOCK",
    ):
        require(marker in header, f"canonical uv-lock workflow missing bootstrap marker: {marker}")
    require("contents: write" not in header, "canonical uv-lock workflow must not grant write permission at workflow scope")

    regenerate = job_block(text, "regenerate-lock", "commit-lock")
    commit = job_block(text, "commit-lock", None)

    for marker in (
        "permissions:\n      contents: read\n",
        "ref: ${{ inputs.expected_sha }}",
        "persist-credentials: false",
        'test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"',
        "python3 scripts/validate_release_action_pins.py",
        "python3 scripts/validate_uv_lock_regeneration_contract.py",
        "run: uv lock",
        "python3 scripts/validate_uv_workspace_lock.py",
        "run: uv lock --check",
        "run: uv sync --all-packages --frozen",
        "sha256sum uv.lock",
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
    ):
        require(marker in regenerate, f"read-only uv-lock regeneration missing marker: {marker}")
    require("contents: write" not in regenerate, "resolver/project-code phase must never receive contents:write")
    require("GITHUB_TOKEN" not in regenerate, "resolver/project-code phase must not receive GitHub write token")
    require("git push" not in regenerate and "git commit" not in regenerate, "read-only resolver phase must not mutate repository refs")

    for marker in (
        "needs: [regenerate-lock]",
        "needs.regenerate-lock.outputs.changed == 'true'",
        "permissions:\n      contents: write\n",
        "ref: ${{ inputs.expected_sha }}",
        "persist-credentials: false",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        "EXPECTED_LOCK_SHA256: ${{ needs.regenerate-lock.outputs.lock_sha256 }}",
        'test ! -L "$artifact"',
        "find _node73-lock-artifact -type f",
        'test "$(sha256sum "$artifact" | awk \'{print $1}\')" = "$EXPECTED_LOCK_SHA256"',
        'test "${changed[0]}" = "uv.lock"',
        'test "$(git rev-parse "origin/${TARGET_REF}")" = "$EXPECTED_SHA"',
        "git add -- uv.lock",
        'test "$(git diff --cached --name-only)" = "uv.lock"',
        'git commit -m "chore(release): regenerate canonical uv lock"',
        'push origin "HEAD:${TARGET_REF}"',
    ):
        require(marker in commit, f"isolated uv-lock write phase missing marker: {marker}")

    require("uv lock" not in commit, "write-capable phase must not run dependency resolver")
    require("uv sync" not in commit, "write-capable phase must not execute project dependency installation")
    require("python3 scripts/" not in commit, "write-capable phase must not execute release-branch Python scripts")
    require(commit.count("GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}") == 1, "write token must be injected into exactly one fixed mutation step")

    lower = text.casefold()
    require("git push --force" not in lower and "git push -f" not in lower, "canonical uv-lock workflow must never force-push")
    require("git add ." not in text and "git add -A" not in text and "git add --all" not in text, "canonical uv-lock workflow must not stage unrelated paths")
    require(text.count("git add -- uv.lock") == 1, "canonical uv-lock workflow must stage uv.lock exactly once")

    read_checkout = regenerate.find("ref: ${{ inputs.expected_sha }}")
    resolver = regenerate.find("run: uv lock")
    artifact = regenerate.find("actions/upload-artifact@")
    write_checkout = commit.find("ref: ${{ inputs.expected_sha }}")
    download = commit.find("actions/download-artifact@")
    remote_guard = commit.find('test "$(git rev-parse "origin/${TARGET_REF}")" = "$EXPECTED_SHA"')
    push = commit.find('push origin "HEAD:${TARGET_REF}"')
    require(min(read_checkout, resolver, artifact, write_checkout, download, remote_guard, push) >= 0, "uv-lock two-phase ordering markers incomplete")
    require(read_checkout < resolver < artifact, "read-only phase must bind exact SHA before resolver and artifact publication")
    require(write_checkout < download < remote_guard < push, "write phase must bind exact SHA/artifact and re-check remote before push")

    print("NODE-73 canonical uv-lock two-phase bootstrap contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LockWorkflowContractError, OSError) as exc:
        raise SystemExit(f"uv-lock regeneration contract failed: {exc}") from exc
