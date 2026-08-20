# NODE-73 — Default-Branch Dispatch Bootstrap Closure

Status: **DISPATCH DISCOVERY BOOTSTRAP IMPLEMENTED; LIVE REGISTRY VERIFICATION ADDED; HOSTED EXECUTION AND FINAL ACCEPTANCE STILL BLOCKED**

This report records the corrected NODE-73 GitHub Actions bootstrap model. It does not claim that `uv.lock` has been regenerated, that any release-critical hosted job has executed successfully, or that Final Acceptance has passed.

## 1. Bootstrap problem

GitHub `workflow_dispatch` requires the workflow path to exist on the repository default branch. The repository default branch is `main`.

Before this closure, NODE-71～73 release-critical workflow paths existed only on `release-closure-p0`, so their manual-dispatch entry points were not discoverable before merge.

## 2. Corrected default-branch model

Current audited default-branch snapshot:

```text
repository: zhangjaky71-stack/LUMI-AI-DESIGN-OS
default branch: main
main snapshot: f424068181b2503bdc81b71e7407022626f4535c
```

All nine release-critical workflow paths from `production/release-actions/pins-v1.json` now exist on `main`:

```text
.github/workflows/assemble-final-acceptance.yml
.github/workflows/build-runtime-image-set.yml
.github/workflows/configure-release-branch-protection.yml
.github/workflows/regenerate-uv-lock.yml
.github/workflows/runtime-image-closure-contract.yml
.github/workflows/staging-acceptance-gate.yml
.github/workflows/production-iac-contract.yml
.github/workflows/deploy-production.yml
.github/workflows/final-acceptance-gate.yml
```

All nine are now **fail-closed registry stubs** on `main`.

Each default-branch stub is constrained to:

```text
workflow_dispatch
contents: read
no secrets
no environment
no external action uses
no repository/package/attestation/OIDC write capability
default-branch-registry-only job
explicit exit 64
```

The default branch therefore provides discovery only. It does not contain the NODE-73 release execution authority.

## 3. Release-ref execution remains canonical

The intended operator path is:

```text
select the registered workflow
select ref = release-closure-p0
provide the required inputs
GitHub executes the hardened workflow definition from release-closure-p0
```

The hardened `release-closure-p0` workflows must not be registry stubs.

In particular, the real `regenerate-uv-lock.yml` on `release-closure-p0` retains the two-phase least-privilege design:

### Read-only resolver phase

```text
contents: read
exact expected SHA checkout
persist-credentials: false
Python 3.12
uv 0.11.28
uv lock
only uv.lock may change
validate workspace membership
uv lock --check
uv sync --all-packages --frozen
freeze uv.lock SHA-256
upload same-run artifact
```

### Isolated write phase

```text
needs successful resolver phase
contents: write
exact expected SHA checkout
persist-credentials: false
download same-run uv.lock artifact
verify exact artifact SHA-256
verify only uv.lock differs
no uv lock
no uv sync
no release-branch Python execution
re-fetch release-closure-p0
require remote head == expected SHA
stage only uv.lock
non-force push
```

This write logic is intentionally absent from `main`.

## 4. Static dispatch registry contract

Committed policy:

```text
production/release-actions/default-branch-dispatch-registry-v1.json
```

Static validator:

```text
scripts/validate_release_dispatch_registry_contract.py
```

It requires:

```text
repository == zhangjaky71-stack/LUMI-AI-DESIGN-OS
default branch == main
release ref == release-closure-p0
registry paths == exactly pins-v1.json release_critical_workflows
all nine default_branch_mode values == FAIL_CLOSED_REGISTRY_STUB
all release-ref workflows still contain workflow_dispatch
release-ref workflows are not registry stubs
release-ref regenerate-uv-lock.yml still contains the hardened two-phase implementation
```

`validate_release_action_pins.py` invokes this contract, so registry policy drift is part of the existing release source gate.

The static contract validates the committed policy and Evidence-Head checkout. It does **not** claim that it can observe the live `main` branch.

## 5. Live default-branch verification

Runtime verifier:

```text
scripts/validate_live_default_branch_dispatch_registry.py
```

Final Decision now uses the ephemeral read-only GitHub token to fetch live `main` and validates every registered workflow path.

For each path it requires:

```text
file exists on live main
contents: read only
no write capabilities
no environment
no secrets
no external actions
registry-only fail-closed job
exit 64
release-closure-p0 execution instruction
workflow_dispatch input schema exactly matches the Evidence-Head hardened workflow
```

It records:

```text
main head SHA
per-workflow Git blob SHA
per-workflow source SHA-256
dispatch input names
input-schema SHA-256
```

Runtime artifact:

```text
reports/final-acceptance/<release-id>/runtime-v2/default-branch-dispatch-registry-live.json
```

`final-acceptance-decision-v2.py` hash-binds this live report and the committed registry policy into the outer final decision.

Therefore deletion, privilege escalation, secret injection, successful default-branch execution, or dispatch-input drift on `main` blocks Final Acceptance.

## 6. Relevant commits

Release branch:

```text
f394322f2e650d16e481fcdcdbb742e513b4c20e  split uv lock read/write phases
328e7054c3adfec96810fec370620a22bd4b2ef7  scope uv-lock write capability
bf44f1dacb1af2ba2c6f7367c85ad6dd55c91e9a  align registry policy to 9/9 stubs
085aafa8d76f03d58c9c98336588840d2cb91484  align static registry contract
c03d84ef1475c000021411f1f232178fcce2c358  add live default-branch registry verifier
63884ac6ddeb9a69089db1c50fd662ef1aaa815b  bind live registry into Final Decision
ed63355da284e122eda3d6aa6d6d898d228c35a8  add V2 anti-regression coverage
```

Default branch:

```text
f424068181b2503bdc81b71e7407022626f4535c  standardize final uv-lock registry stub
```

## 7. Closed vs blocked

Closed at source/repository bootstrap level:

```text
workflow_dispatch discoverability for all nine release-critical paths
default branch contains no NODE-73 privileged release execution logic
release-ref uv-lock resolver/write-token separation
static registry policy coverage
Final Decision live registry verification design
```

Still blocked until real execution/configuration exists:

```text
actual hosted execution of regenerate-uv-lock
actual canonical uv.lock output
uv lock --check PASS
uv sync --all-packages --frozen PASS
trusted release source/runtime/PostgreSQL/Staging/Production evidence
strong branch protection applied live
real human approvals
successful runtime live-registry capture during Final Decision
Final Decision accepted=true
```

No zero-step hosted run is treated as an application failure or PASS.

# KEEP NODE-73 FINAL ACCEPTANCE BLOCKED
