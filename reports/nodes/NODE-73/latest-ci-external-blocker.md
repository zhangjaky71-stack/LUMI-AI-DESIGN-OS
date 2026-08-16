# NODE-73 — Latest Hosted CI External Blocker

Status: **BLOCKED_EXTERNAL**

This record captures the latest hosted execution state observed after the NODE-73 Final Acceptance hard-stop/UAT/signoff/Stripe/source-RC identity and canonical lock-repair changes. It is not a test PASS or source-code FAIL.

## Exact observed head

- branch: `fix/final-acceptance-hard-stops`
- head SHA observed for this record: `d76cea2cb1dc7753b7af2f341717206705f646b0`
- PR: `#80`
- PR state at observation: open, `mergeable=true`

## Final Product Acceptance Gate

- workflow: `Final Product Acceptance Gate`
- run id: `31930871336`
- head SHA: `d76cea2cb1dc7753b7af2f341717206705f646b0`
- `canonical-lock-gate` job id: `95125379164` — failure before executable steps;
- `source-contract` job id: `95125379185` — failure before executable steps;
- `lock-repair-artifact` job id: `95125379254` — failure before executable steps;
- `final-decision` — skipped because this was not a manual final-decision dispatch;
- `contract-gate` — cannot become green while its required upstream jobs never start.

The `lock-repair-artifact` job is particularly useful diagnostic evidence because it does **not** depend on the stale committed lock being valid before it can regenerate it. GitHub nevertheless reports:

```text
runner_id=0
runner_name=""
runner_group_id=0
steps=[]
```

and the check annotation is exactly:

```text
The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings
```

Therefore the repair job did not execute `uv`, the regeneration script, dependency resolution, frozen sync, or artifact upload. This is an account-level hosted-runner blocker, not a lock-generation failure.

## Same-head workflow pattern

The same SHA produced completed red runs across CI, Database Schema, Production IaC, Model Gateway, Recovery, Performance, Observability, Security Release Gate, AI Regression, Staging Acceptance, Final Browser Preflight, Final Production Safety Hard Stops and many subsystem workflows. This broad simultaneous zero-execution pattern is consistent with the confirmed account Billing/spending-limit failure above.

Do not infer source regressions from those red statuses until a job has both:

1. a non-zero allocated runner; and
2. actual executable steps.

## Independent source blocker: stale root `uv.lock`

The root `uv.lock` remains stale relative to the current workspace manifest. That is independent of the GitHub account blocker and remains:

```text
FAIL / SOURCE BLOCKER
```

The guarded local regeneration entry point is:

```bash
scripts/regenerate-root-uv-lock.sh
```

It requires:

- Python `3.12.x`;
- uv exactly `0.11.28`;
- clean manifest/lock inputs;
- `uv lock`;
- `uv lock --check`;
- `uv sync --all-packages --frozen`;
- every workspace member represented in `uv.lock`;
- an actual lock change;
- no collateral source changes.

The `Final Product Acceptance Gate` also contains an independent `lock-repair-artifact` job that uses Python 3.12 + uv 0.11.28, runs the same canonical repair guard when the lock is stale, re-validates frozen installation, and uploads `canonical-root-uv-lock-<run-id>` for review. It has read-only repository permissions and is statically forbidden from `git commit`/`git push`; producing an artifact does not make the canonical lock gate PASS.

The current ChatGPT container exposes Python `3.13.5` and uv `0.10.0`. Attempts to obtain the required binary/repository through the isolated container network are blocked by DNS/download restrictions. Generating and committing a release lock with these non-canonical local tools would violate the release contract, so it is intentionally not done.

## Final Acceptance identity source closure

The canonical runner now separates:

- frozen **source RC SHA**;
- later **evidence checkout SHA**.

The source RC must be an ancestor of the evidence checkout. Every commit after source-RC freeze is audited with Git history and may touch only `reports/`; a source path changed and later reverted still invalidates the RC. Root `VERSION` and the unique Alembic head must remain the same. All six upstream decisions must carry the same source-RC tuple. The final-decision workflow uses full Git history (`fetch-depth: 0`) and persists `release-identity-decision.json` alongside manual/final decisions.

These source controls are still **VALIDATION_PENDING** until a real runner executes their negative contracts.

## Classification rule

Use:

```text
BLOCKED_EXTERNAL
```

for hosted jobs that do not receive a runner.

Keep the stale dependency lock separately classified as:

```text
FAIL / SOURCE BLOCKER
```

Do not use `PASS`, `FAIL_CODE`, `SOURCE_TEST_FAILED`, or `BROWSER_REGRESSION_FAILED` for a zero-runner / zero-step account Billing failure.

## Required recovery order

1. restore GitHub Actions account payment/spending-limit ability **or** obtain a clean external environment with Python 3.12 + uv 0.11.28;
2. run the canonical lock repair path and review the generated `uv.lock`;
3. commit the genuinely generated lock before source-RC freeze;
4. trigger fresh workflows and verify `runner_id != 0` plus real steps;
5. run canonical CI, Security, Recovery, Performance, AI Regression, Staging Acceptance, Final Production Safety Hard Stops, Final Browser Preflight and Final Product Acceptance source contracts;
6. fix any real executable source/test failures that appear;
7. only then freeze the final source RC and create its 50-scenario evidence skeleton;
8. collect real AWS/Stripe/UAT/browser/accessibility/signoff evidence using reports-only commits after the source RC;
9. run the canonical final decision from a clean full-history evidence checkout.

NODE-73 remains **NOT ACCEPTED**.
