# NODE-73 — Latest Hosted CI External Blocker

Status: **BLOCKED_EXTERNAL**

This record captures the latest hosted execution state observed after the NODE-73 Final Acceptance hard-stop/UAT/signoff/manual-evidence/Stripe source changes and the canonical lock-regeneration helper. It is not a test PASS or source-code FAIL.

## Exact observed head

- branch: `fix/final-acceptance-hard-stops`
- head SHA observed for this record: `5fb99259b4395ef25c0c552b2ed3c9cad10971e2`
- PR: `#80`
- PR mergeability at observation: `mergeable=true`

## Final Production Safety Hard Stops

- workflow: `Final Production Safety Hard Stops`
- run id: `31930129068`
- head SHA: `5fb99259b4395ef25c0c552b2ed3c9cad10971e2`
- `static-contract` job id: `95123554417`
- job conclusion: `failure`
- executable steps returned by GitHub: `null`
- downstream `terraform-format`, `quality`, and `postgres-acceptance`: skipped

The immediately preceding exact-head run on SHA `b749920df0aee6d83764c60cb4ff37cf7ab43524` established the same account-level failure shape with:

- `runner_id=0`;
- `runner_name=""`;
- `steps=[]`;
- one GitHub check annotation stating:

```text
The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings
```

The new head continues the same zero-execution pattern across repository workflows. No evidence indicates that an executable source step ran and failed.

## Other workflows on the same head

The same SHA produced completed red runs across canonical CI, Database Schema, Production IaC, Model Gateway, Observability, browser preflight, security-adjacent and multiple subsystem workflows while several other runs remained queued/in-progress at observation time. The completed failures share the hosted-runner non-execution pattern seen on the prior exact head.

Do not infer a source regression from the red status until a job has both:

1. a non-zero allocated runner; and
2. actual executable steps.

## Known independent source blocker

The root `uv.lock` remains stale relative to the current workspace manifest. That is independent of the GitHub account blocker and is expected to fail canonical frozen installation once hosted runners are restored unless repaired first.

A guarded regeneration entry point now exists:

```bash
scripts/regenerate-root-uv-lock.sh
```

The script refuses to run unless:

- Python is `3.12.x`;
- uv is exactly `0.11.28`;
- manifest/lock inputs are clean before regeneration.

It then runs `uv lock`, `uv lock --check`, `uv sync --all-packages --frozen`, verifies every workspace member exists in `uv.lock`, requires the lock to actually change, and rejects collateral file changes. It does not hand-edit or synthesize the lock.

This ChatGPT execution environment currently exposes uv `0.10.0`, not the required `0.11.28`, so regenerating and committing a release lock from this environment would violate the canonical dependency contract.

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

## Required recovery

1. on a clean checkout, install/use Python 3.12 and uv 0.11.28;
2. run `scripts/regenerate-root-uv-lock.sh`, review the generated `uv.lock` diff, and commit the generated lock normally;
3. restore GitHub Actions account payment/spending-limit ability;
4. trigger fresh workflows for the exact post-lock release candidate;
5. verify `runner_id != 0` and actual steps execute;
6. run canonical CI, Security, AI Regression, Staging Acceptance, Final Production Safety Hard Stops, Final Browser Preflight and Final Product Acceptance source contracts;
7. classify real source/test results only after executable steps exist;
8. continue the separate real AWS/Stripe/UAT/signoff evidence plan only against that exact frozen candidate.

NODE-73 remains **NOT ACCEPTED**.
