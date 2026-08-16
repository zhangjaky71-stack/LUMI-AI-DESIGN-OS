# NODE-73 — Exact Release Identity Source Closure

Status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This record closes release-authorization identity gaps discovered during Final Acceptance review. It does **not** change NODE-73 to ACCEPTED.

## Gaps found

The prior source contract strongly bound evidence records to each other, but the canonical release authorization path still had four identity/reuse risks:

1. a complete evidence/signoff package for an older source RC could be evaluated without proving that current source still represented that RC;
2. `version` and `migration_head` could be internally consistent across JSON evidence while not matching the repository root `VERSION` or the actual Alembic graph head;
3. only a subset of required upstream decisions were forced to carry exact release-candidate identity, allowing old Security or Recovery decisions to be reused with a newer candidate;
4. a naive rule requiring the release manifest Git SHA to equal the checkout HEAD would be impossible once the manifest/evidence/signoff files themselves are committed, because those evidence commits necessarily change HEAD.

The acceptance invariant requires one exact **source RC** while still allowing later evidence commits. The implementation therefore uses a source-RC/evidence-checkout model rather than a self-referential single SHA.

## Source closure implemented

### Source RC plus evidence checkout

The canonical `scripts/run-final-acceptance.py` now distinguishes:

- `release_candidate.git_sha`: the frozen product/source RC commit;
- current checkout HEAD: the evidence checkout containing frozen reports/signoffs for that RC.

The source RC must:

1. exist as a local Git commit;
2. be an ancestor of the evidence checkout HEAD;
3. have the same root `VERSION` and unique Alembic head as the evidence checkout;
4. have **no post-RC source changes**.

The only committed paths permitted between:

```text
release_candidate.git_sha .. current HEAD
```

are paths under:

```text
reports/
```

This allows release evidence, production deployment manifests, structured UAT evidence and signoff records to be committed after the source RC freeze without changing the product RC.

Any post-RC change to application/service code, workflows, scripts, IaC, lockfiles, `VERSION`, Final Acceptance definitions or other non-report source invalidates the frozen RC and fails closed with:

```text
FINAL_ACCEPTANCE_POST_RC_SOURCE_CHANGE
```

The canonical runner also requires a clean Git worktree before release authorization so local uncommitted source/evidence cannot silently influence the decision.

### Repository version and migration binding

The runner derives repository source facts using only local source state:

- release version from root `VERSION`;
- migration head by statically parsing every `apps/api/alembic/versions/*.py` revision/down-revision edge and requiring exactly one graph head.

The release manifest's version and migration head must equal those repository facts. Mismatch fails closed with:

```text
FINAL_ACCEPTANCE_REPOSITORY_IDENTITY_MISMATCH
```

The migration resolver rejects duplicate revisions, unknown parents, unsupported down-revision shapes and multiple heads.

### All upstream gates bind the same source RC

The canonical runner reads `required_upstream_gates` from `final/acceptance/manifest-v1.json` instead of maintaining a partial hard-coded identity list.

Every required upstream decision must carry the same full `release_candidate` tuple as the final release manifest. At the current matrix this includes exactly:

- Security;
- Recovery;
- Performance;
- AI Regression;
- Staging Acceptance;
- Production Deployment.

Any mismatch fails closed with:

```text
FINAL_ACCEPTANCE_UPSTREAM_RC_MISMATCH
```

The existing frozen-file SHA validation in the low-level final gate remains mandatory; exact-RC preflight adds identity binding and does not replace evidence hashing.

### Negative contract proof

`scripts/validate_final_runner_checkout_binding.py` now proves that:

- `reports/` is the only accepted post-RC evidence namespace;
- changes to `scripts/`, `apps/`, `services/`, `infra/`, `VERSION`, `uv.lock` or `final/acceptance/` are not evidence-only changes;
- a release version different from root `VERSION` is rejected;
- a migration head different from the repository's unique Alembic head is rejected;
- a stale Security upstream decision bound to another RC is rejected;
- all required upstream decisions bind successfully for a clean matching source fixture.

The `Final Product Acceptance Gate` source-contract job runs this validator and compiles the runner/validator sources.

### Safer evidence skeleton generation

`scripts/create-final-acceptance-evidence.py` no longer requires the operator to manually copy Git SHA, version or migration head.

At source-RC freeze time it:

- derives the exact current Git SHA, root `VERSION` and unique Alembic head using the canonical runner;
- optionally accepts identity CLI flags only as assertions that must equal repository truth;
- validates a safe release ID;
- generates all scenario IDs from the canonical matrix;
- rejects duplicate/invalid scenario IDs;
- writes only under `reports/final-acceptance/<release-id>/acceptance-evidence.json`;
- refuses to overwrite an existing evidence file;
- initializes every scenario to `NOT_RUN`, which cannot satisfy Final Acceptance.

After that source freeze, subsequent commits used for final authorization must be evidence-only `reports/` commits or the RC must be frozen again.

## Dependency lock repair guard

The root `uv.lock` remains a real source blocker because the current ChatGPT execution environment does not have the required canonical uv version.

`scripts/regenerate-root-uv-lock.sh` provides the guarded repair procedure for this branch. It requires:

- Python 3.12.x;
- uv exactly 0.11.28;
- clean manifest/lock inputs;
- `uv lock`;
- `uv lock --check`;
- `uv sync --all-packages --frozen`;
- every workspace member represented in the generated lock;
- an actual `uv.lock` change;
- no collateral source-file changes.

The upstream-lock static validator and Final Product Acceptance workflow enforce the helper contract/syntax.

The current model execution environment exposes uv 0.10.0, therefore it is intentionally not used to regenerate the release lock.

## Still required before acceptance

- regenerate and commit `uv.lock` using the canonical helper on Python 3.12 + uv 0.11.28;
- complete any remaining source changes before freezing the final source RC;
- create the 50-scenario evidence skeleton at that source RC;
- after RC freeze, commit only `reports/` evidence/signoff material or deliberately invalidate and refreeze the RC;
- restore hosted GitHub Actions runner allocation;
- execute the release identity/upstream negative contract on a real runner;
- collect and hash all required automated/manual/runtime evidence;
- bind all six upstream decisions to the frozen source RC tuple;
- bind all eight human signoff records to the frozen source RC tuple;
- run the canonical final runner from a clean evidence checkout descended from the source RC with reports-only changes.

## Final status

NODE-73 remains **NOT ACCEPTED**. The corrected model prevents stale RC reuse and source drift while avoiding an impossible self-referential Git SHA requirement for evidence commits.
