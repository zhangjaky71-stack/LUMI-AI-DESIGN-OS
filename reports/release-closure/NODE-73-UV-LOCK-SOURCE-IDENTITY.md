# NODE-73 Canonical `uv.lock` Source Identity Closure

Status: **IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Scope: NODE-73 Release Closure only. This document does not claim that `uv.lock` has been regenerated and does not change the Final Acceptance verdict.

## P0 finding

The canonical lock regeneration workflow was already constrained to `release-closure-p0`, used the pinned `uv 0.11.28` resolver, required `uv.lock` to be the only generated change, ran `uv lock --check` plus `uv sync --all-packages --frozen`, and pushed without force.

However, checkout still used the movable branch ref `${{ github.ref_name }}`. The workflow did not prove that the checked-out source revision remained equal to the workflow-dispatch `GITHUB_SHA` before regenerating the lock.

That left a dispatch-to-checkout source identity race: a branch move could cause the lock to be regenerated from a different source revision than the one associated with the workflow run.

## Implemented closure

### Exact dispatch-SHA checkout

`.github/workflows/regenerate-uv-lock.yml` now checks out:

```text
ref: ${{ github.sha }}
```

instead of the movable branch name.

Before `uv lock`, the workflow requires:

```text
test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
```

and a clean worktree.

### Branch-move barrier before commit

After canonical lock generation and frozen verification, but before creating the commit, the workflow refreshes the remote release branch and requires:

```text
origin/${GITHUB_REF_NAME} == GITHUB_SHA
```

If another commit advanced `release-closure-p0` while the workflow was running, regeneration blocks instead of committing a lock generated from a stale parent.

The subsequent push remains a normal non-force push, providing a second race-safe fail-closed barrier if the branch moves after the remote comparison.

### Narrow mutation scope

The workflow continues to require:

- only `uv.lock` differs after resolver execution;
- only `uv.lock` is staged;
- no `git add .`, `git add -A`, or `git add --all` behavior;
- no force push;
- branch identity remains exactly `release-closure-p0`.

### Anti-regression contract

Added `scripts/validate_uv_lock_regeneration_contract.py`.

It blocks removal or weakening of:

- exact `github.sha` checkout;
- `HEAD == GITHUB_SHA` source binding;
- immutable Action pin validation;
- exact `uv lock` mutation point;
- remote branch `== GITHUB_SHA` barrier before commit;
- `uv.lock`-only staging;
- non-force push behavior;
- required ordering from source binding -> mutation -> branch re-check -> commit -> push.

The contract is self-invoked by the manual lock-regeneration workflow before mutation and is also wired into Runtime Image Closure and NODE-73 Final Acceptance source validation.

## Commits

- `a59d44a2d5fa6d386b1b6a5c82ef820fb9bc616e` — bind lock regeneration to dispatch SHA and branch-move barrier.
- `ff114a0080a8d78ee97e870f12afb0a163e1b0ce` — add fail-closed source-identity contract.
- `0646288753371c3780fbe29c1663cda3e3a33bf6` — self-gate source identity before lock mutation.
- `3496b3f05846c1c39c8c434d1ec2c87c8f8b6eb5` — Runtime Image Closure integration.
- `274f58bbee0be7f758715aef0d8c381ff1b58c6f` — Final Acceptance integration.

## What is not claimed

The checked-in `uv.lock` remains stale. This closure only fixes the provenance and race properties of the canonical regeneration path.

A trusted runnable environment still must execute the workflow (or an equivalent audited process) and produce real evidence for:

1. `uv lock` using the pinned resolver;
2. exact workspace membership validation;
3. `uv lock --check`;
4. `uv sync --all-packages --frozen`;
5. release Python contract compilation;
6. the single-file `uv.lock` commit on the unmoved release branch.

Hosted GitHub Actions have continued to exhibit the established zero-step external failure pattern, so no runtime PASS is claimed here.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The lock regeneration path is now source-identity safe and fail-closed, but the canonical lock itself is not accepted until trusted execution actually regenerates and validates it.
