# NODE-73 — Exact Release Identity Source Closure

Status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This record closes release-authorization identity gaps discovered during Final Acceptance review. It does **not** change NODE-73 to ACCEPTED.

## Gaps found

The prior source contract strongly bound evidence records to each other, but the canonical release authorization path still had three reuse risks:

1. a complete evidence/signoff package for an older Git SHA could be evaluated from a newer checkout because the release manifest SHA was not compared to the actual repository HEAD;
2. `version` and `migration_head` could be internally consistent across JSON evidence while not matching the repository root `VERSION` or the actual Alembic graph head;
3. only a subset of required upstream decisions were forced to carry exact release-candidate identity, allowing old Security or Recovery decisions to be reused with a newer candidate.

The acceptance invariant requires one exact RC, so all three are release-authority gaps.

## Source closure implemented

### Repository identity binding

The canonical `scripts/run-final-acceptance.py` now computes repository truth using only local immutable source state:

- Git SHA from `git rev-parse HEAD`;
- release version from root `VERSION`;
- migration head by statically parsing every `apps/api/alembic/versions/*.py` revision/down-revision edge and requiring exactly one graph head.

Before any manual-evidence or final-decision evaluator runs, the release manifest must match the exact tuple:

```text
(git_sha, VERSION, unique_alembic_head)
```

Mismatch fails closed with `FINAL_ACCEPTANCE_REPOSITORY_IDENTITY_MISMATCH`.

The migration resolver also rejects duplicate revisions, unknown parents, unsupported down-revision shapes and multiple heads.

### All upstream gates bind the same RC

The canonical runner reads `required_upstream_gates` from `final/acceptance/manifest-v1.json` instead of maintaining a partial hard-coded identity list.

Every required upstream decision must now contain a `release_candidate` tuple equal to the final release manifest. At the current matrix this includes exactly:

- Security;
- Recovery;
- Performance;
- AI Regression;
- Staging Acceptance;
- Production Deployment.

Any mismatch fails closed with `FINAL_ACCEPTANCE_UPSTREAM_RC_MISMATCH` before the final decision gate runs.

The existing frozen-file SHA validation in the low-level final gate remains mandatory; this new preflight adds exact-RC identity, it does not replace evidence hashing.

### Negative contract proof

`scripts/validate_final_runner_checkout_binding.py` now proves that the canonical runner rejects:

- a stale Git SHA;
- a release version different from root `VERSION`;
- a migration head different from the repository's unique Alembic head;
- a stale Security upstream decision bound to another RC.

It also proves the clean current repository identity and all required upstream bindings are accepted by the source preflight.

The `Final Product Acceptance Gate` source-contract job runs this validator and compiles the runner/validator sources.

### Safer evidence skeleton generation

`scripts/create-final-acceptance-evidence.py` no longer requires the operator to manually copy Git SHA, version or migration head.

It now:

- derives the exact repository identity using the canonical runner;
- optionally accepts identity CLI flags only as assertions that must equal repository truth;
- validates a safe release ID;
- generates all scenario IDs from the canonical matrix;
- rejects duplicate/invalid scenario IDs;
- writes only under `reports/final-acceptance/<release-id>/acceptance-evidence.json`;
- refuses to overwrite an existing evidence file;
- initializes every scenario to `NOT_RUN`, which cannot satisfy Final Acceptance.

This reduces operator error without manufacturing PASS evidence.

## Dependency lock repair guard

The root `uv.lock` remains a real source blocker because the current ChatGPT execution environment does not have the required canonical uv version.

`scripts/regenerate-root-uv-lock.sh` now provides the only documented repair procedure for this branch. It requires:

- Python 3.12.x;
- uv exactly 0.11.28;
- clean manifest/lock inputs;
- `uv lock`;
- `uv lock --check`;
- `uv sync --all-packages --frozen`;
- every workspace member represented in the generated lock;
- an actual `uv.lock` change;
- no collateral source-file changes.

The upstream-lock static validator and Final Product Acceptance workflow both enforce the helper contract/syntax.

The current model execution environment exposes uv 0.10.0, therefore it is intentionally not used to regenerate the release lock.

## Still required before acceptance

- regenerate and commit `uv.lock` using the canonical helper on Python 3.12 + uv 0.11.28;
- restore hosted GitHub Actions runner allocation;
- execute the checkout/upstream identity negative contract on a real runner;
- freeze one final candidate only after all source changes are complete;
- generate the initial 50-scenario evidence skeleton from that exact checkout;
- collect and hash all required automated/manual/runtime evidence;
- bind all six upstream decisions to that exact tuple;
- bind all eight human signoff records to that exact tuple;
- rerun the canonical final runner after the final evidence/signoff change.

## Final status

NODE-73 remains **NOT ACCEPTED**. These changes prevent a prior release package, stale Security/Recovery decision, mistyped version or mistyped migration head from authorizing a different checkout.
