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


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")

    required = (
        "workflow_dispatch:",
        "contents: write",
        "github.ref_type == 'branch' && github.ref_name == 'release-closure-p0'",
        "ref: ${{ github.sha }}",
        'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
        "python3 scripts/validate_release_action_pins.py",
        "run: uv lock",
        'test "$(git diff --cached --name-only)" = "uv.lock"',
        'git fetch --no-tags origin "+refs/heads/${GITHUB_REF_NAME}:refs/remotes/origin/${GITHUB_REF_NAME}"',
        'test "$(git rev-parse "origin/${GITHUB_REF_NAME}")" = "$GITHUB_SHA"',
        'git push origin "HEAD:${GITHUB_REF_NAME}"',
    )
    for marker in required:
        require(marker in text, f"canonical uv-lock workflow missing source-identity marker: {marker}")

    require(
        "ref: ${{ github.ref_name }}" not in text,
        "canonical uv-lock workflow must not checkout a movable branch ref",
    )
    lower = text.casefold()
    require("git push --force" not in lower, "canonical uv-lock workflow must never force-push")
    require("git push -f" not in lower, "canonical uv-lock workflow must never force-push")

    pin_pos = text.find("python3 scripts/validate_release_action_pins.py")
    head_pos = text.find('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"')
    lock_pos = text.find("run: uv lock")
    remote_pos = text.find('test "$(git rev-parse "origin/${GITHUB_REF_NAME}")" = "$GITHUB_SHA"')
    commit_pos = text.find('git commit -m "chore(release): regenerate canonical uv lock"')
    push_pos = text.find('git push origin "HEAD:${GITHUB_REF_NAME}"')
    require(
        min(pin_pos, head_pos, lock_pos, remote_pos, commit_pos, push_pos) >= 0,
        "canonical uv-lock workflow source-identity ordering markers are incomplete",
    )
    require(
        pin_pos < head_pos < lock_pos < remote_pos < commit_pos < push_pos,
        "canonical uv-lock workflow must bind action pins and dispatch SHA before mutation, then re-check branch before commit/push",
    )

    require(
        text.count("git add -- uv.lock") == 1,
        "canonical uv-lock workflow must stage only the lock file exactly once",
    )
    require(
        "git add ." not in text and "git add -A" not in text and "git add --all" not in text,
        "canonical uv-lock workflow must not stage unrelated paths",
    )

    print("NODE-73 canonical uv-lock regeneration source-identity contract: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LockWorkflowContractError, OSError) as exc:
        raise SystemExit(f"uv-lock regeneration contract failed: {exc}") from exc
