# NODE-73 Release Workflow Least-Privilege Closure

Status: **IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Scope: NODE-73 Release Closure only. This evidence does not introduce NODE-74 and does not change the Final Acceptance verdict.

## P0 finding

The release chain had strong source, artifact, digest, provenance, and Action-pin controls, but several workflow permissions were broader than the job that actually needed them:

- `deploy-production.yml` granted `id-token: write` at workflow scope, so the read/validation `release-gate` inherited OIDC token-minting capability before NODE-71 and the production manifest had been accepted.
- `staging-acceptance-gate.yml` granted `actions: read` at workflow scope even though only the dispatch-only `acceptance-decision` job needs cross-run artifact download.
- `build-runtime-image-set.yml` granted package/attestation/OIDC write capability to the same job that performed source and canonical-lock validation, instead of making write capability conditional on a prior read-only gate.

## Implemented closure

### Six-runtime RC build: read-only prerequisite gate

`build-runtime-image-set.yml` now defaults to:

```text
permissions:
  contents: read
```

A new `source-gate` job has explicit `contents: read` only. It uses exact `github.sha` checkout and must pass:

- immutable Action pin policy;
- canonical `uv.lock` regeneration source-identity contract;
- runtime image source closure;
- runtime image manifest contract;
- runtime image build/freeze anti-regression contract;
- runtime image-set contract;
- exact workspace lock membership;
- `uv lock --check`;
- `uv sync --all-packages --frozen`.

Only after `source-gate` succeeds can `build-and-freeze` run via:

```text
needs: [source-gate]
```

That job alone receives:

```text
contents: read
packages: write
attestations: write
id-token: write
```

It re-checks exact `HEAD == GITHUB_SHA` before GHCR login and image mutation.

### NODE-71: cross-run artifact permission scoped to decision job

`staging-acceptance-gate.yml` now defaults to `contents: read` only.

`actions: read` exists only on `acceptance-decision`, the job that downloads the exact six-image build artifact. `source-contract`, `canonical-lock-gate`, and `remote-read-only-preflight` do not receive cross-run Actions read permission.

`validate_staging_runtime_image_workflow_contract.py` now independently enforces this scope in addition to its existing artifact/run/provenance ordering checks.

### NODE-72: OIDC scoped only to protected production job

`deploy-production.yml` now defaults to:

```text
contents: read
actions: read
```

There is no workflow-level `id-token: write`.

The `release-gate` can read the exact NODE-71 artifact but cannot mint OIDC tokens and does not contain the AWS role-assumption action.

Only the downstream `production` job receives:

```text
contents: read
id-token: write
```

and that job remains protected by:

```text
environment: production
needs: [release-gate]
```

The production job does not inherit `actions: read`, because cross-run artifact access is no longer needed after release-gate.

`validate_production_node71_workflow_contract.py` now independently enforces this OIDC boundary alongside exact NODE-71 artifact identity.

### Canonical lock mutation

`regenerate-uv-lock.yml` retains the one intentional repository write permission: `contents: write`. The least-privilege contract rejects unrelated `actions`, package, attestation, or OIDC write capabilities and continues to require `uv.lock`-only staging plus non-force push.

### Read-only release contracts

The following remain top-level `contents: read` only:

- Runtime Image Closure Contract;
- Production IaC Contract;
- Final Product Acceptance Gate.

## Unified anti-regression contract

Added `scripts/validate_release_workflow_permissions.py`.

It covers all seven release-critical workflows and fails closed if:

- package/attestation/OIDC permissions return to the runtime-image workflow top level or read-only source-gate;
- the write-capable runtime build no longer depends on `source-gate`;
- NODE-71 `actions: read` escapes `acceptance-decision`;
- NODE-72 `id-token: write` returns to workflow/release-gate scope;
- NODE-72 OIDC job loses `environment: production` or `needs: [release-gate]`;
- production mutation receives unnecessary cross-run Actions permission;
- `uv.lock` regeneration gains unrelated write capabilities;
- Runtime Closure, Production IaC, or Final Acceptance gain write permissions.

The unified contract is wired into Runtime Image Closure, Production IaC Contract, and NODE-73 Final Acceptance. Domain-specific NODE-71/NODE-72/runtime-image validators provide an additional independent layer.

## Source audit at this checkpoint

Current branch source was re-fetched after the permission changes.

Observed source state:

- Runtime image workflow top-level: `contents: read` only.
- Runtime image `source-gate`: `contents: read` only.
- Runtime image `build-and-freeze`: `contents: read`, `packages: write`, `attestations: write`, `id-token: write`; depends on `source-gate`.
- NODE-71 workflow top-level: `contents: read` only.
- NODE-71 `acceptance-decision`: `contents: read`, `actions: read`.
- NODE-72 workflow top-level: `contents: read`, `actions: read`; no OIDC.
- NODE-72 `release-gate`: no OIDC and no AWS role-assumption action.
- NODE-72 `production`: `contents: read`, `id-token: write`, protected by `environment: production`, depends on `release-gate`.

This is source-level evidence only and is not represented as hosted execution PASS.

## Commits

- `4a315668858ba48c07dc68e105d73d7489322bbb` — scope Production OIDC to mutation job.
- `c7233a886ff67a12d1d68d306c6c72d705bb1862` — scope NODE-71 `actions:read` to acceptance decision.
- `3d964116a407a24aed44ec42c7d2b14742975b4e` — split six-runtime read-only source gate from write-capable build.
- `688388adf863ea7086d42e0af469f9bf63303f10` — enforce read-only source gate in runtime-image pipeline contract.
- `7b9d155720dd5a2ac5a24510dd865527effd596e` — unified release workflow least-privilege validator.
- `30a407598e2ebd1779c85561f221f34c50ca99f6` — Runtime Image Closure integration.
- `15bd32f1f982b353efcbe44ec1ae5252de86c61b` — Final Acceptance integration.
- `f6f1ba83ea46bf8d0a7fc8db506a6cf400d89fdf` — Production IaC integration.
- `49d6ea36aada6ccfd06996bd92ccb483d2e8310a` — NODE-71 scoped-permission anti-regression contract.
- `8e73b18e322c27b5a543fefd7134e8b9826dd0ae` — NODE-72 scoped-OIDC anti-regression contract.

## What is not claimed

This change does not demonstrate successful OIDC issuance, AWS role assumption, image publication, Staging acceptance, or Production deployment. Those require trusted runtime execution.

It does not repair the stale canonical `uv.lock` and does not remove the established GitHub-hosted runner external blocker.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

The release execution graph is now materially narrower in privilege and fail-closed at source level, but NODE-73 still requires real canonical-lock, CI, PostgreSQL, image, Staging, Production, rollback/DR, and approval evidence.
