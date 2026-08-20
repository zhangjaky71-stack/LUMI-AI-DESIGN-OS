# NODE-73 — Default-Branch Dispatch Bootstrap Closure

Status: **DISPATCH DISCOVERY BOOTSTRAP IMPLEMENTED; HOSTED EXECUTION AND FINAL ACCEPTANCE STILL BLOCKED**

This report closes a GitHub Actions bootstrap gap discovered during NODE-73 finalization. It does not claim that `uv.lock` has been regenerated, that any release-critical hosted job has executed successfully, or that Final Acceptance has passed.

## 1. Problem discovered

GitHub `workflow_dispatch` only receives events when the workflow file exists on the repository default branch.

The repository default branch is:

```text
main
```

Before this closure, NODE-71～73 release-critical workflows such as:

```text
.github/workflows/regenerate-uv-lock.yml
.github/workflows/build-runtime-image-set.yml
.github/workflows/staging-acceptance-gate.yml
.github/workflows/deploy-production.yml
.github/workflows/assemble-final-acceptance.yml
.github/workflows/configure-release-branch-protection.yml
.github/workflows/final-acceptance-gate.yml
```

existed on `release-closure-p0` but were absent from `main`. Therefore their manual-dispatch paths were not actually discoverable by GitHub before merge.

This was a bootstrap blocker, independent from the existing zero-step hosted-runner blocker.

## 2. Default-branch registry now exists

Current audited default-branch snapshot after registration:

```text
repository: zhangjaky71-stack/LUMI-AI-DESIGN-OS
default branch: main
main snapshot: fbe3bdf1efb29abb2bbf76c149dfbc3903a490dd
```

The nine release-critical workflow paths from `production/release-actions/pins-v1.json` now all exist on `main`:

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

## 3. Fail-closed registry-stub model

Eight workflows use a default-branch registry-only stub.

The stubs contain only:

```text
workflow_dispatch
contents: read
default-branch-registry-only job
explicit exit 64
```

They do not copy release/production execution logic into `main`, do not expose release secrets, and fail closed if somebody accidentally dispatches the `main` version.

The intended operator path is:

```text
select workflow
select/ref release-closure-p0
provide the required inputs
GitHub executes the workflow version at release-closure-p0
```

This follows GitHub's workflow-dispatch ref semantics while keeping `main` as discovery/bootstrap only.

## 4. Canonical uv.lock bootstrap is intentionally different

`regenerate-uv-lock.yml` is not a stub. `main` and `release-closure-p0` carry the same canonical workflow blob:

```text
workflow blob SHA: d1c4f6d1ab6f6688f2a37cd211b7e9fe76561a50
```

This allows the lock repair to be dispatched from the default branch with an explicit exact `release-closure-p0` SHA even before any release workflow merge.

The workflow now has two isolated jobs.

### Read-only resolver phase

```text
permissions: contents: read
exact expected SHA checkout
persist-credentials: false
Python 3.12
uv 0.11.28
validate immutable Action pins
validate lock source contract
uv lock
only uv.lock may change
validate workspace membership
uv lock --check
uv sync --all-packages --frozen
compile release Python contracts
freeze uv.lock SHA-256
upload same-run artifact
```

The resolver/project-code phase receives no `contents: write` and no explicit `GITHUB_TOKEN` environment variable.

### Isolated write phase

```text
needs successful resolver phase
runs only when uv.lock actually changed
permissions: contents: write
exact expected SHA checkout
persist-credentials: false
download same-run uv.lock artifact
verify exact artifact SHA-256
verify artifact is a regular non-symlink file
verify only uv.lock differs
no uv lock
no uv sync
no release-branch Python scripts
re-fetch release-closure-p0
require remote head == expected SHA
stage only uv.lock
non-force push
```

The repository write token is injected into only the final fixed mutation step.

This removes the previous design where dependency resolution/project code and repository write capability lived in the same job.

## 5. Registry contract

Committed policy:

```text
production/release-actions/default-branch-dispatch-registry-v1.json
```

Validator:

```text
scripts/validate_release_dispatch_registry_contract.py
```

The contract requires:

```text
repository == zhangjaky71-stack/LUMI-AI-DESIGN-OS
default branch == main
release ref == release-closure-p0
registry paths == exactly pins-v1.json release_critical_workflows
exactly nine release-critical workflows
exactly one CANONICAL_TWO_PHASE_BOOTSTRAP entry
that entry == regenerate-uv-lock.yml
all other entries == FAIL_CLOSED_REGISTRY_STUB
all release-ref workflows still contain workflow_dispatch
release-ref workflows may not be registry stubs
```

`validate_release_action_pins.py` now invokes this registry contract, so the policy is part of existing release source gates rather than an orphaned audit file.

## 6. Commits

Release branch source closure:

```text
f394322f2e650d16e481fcdcdbb742e513b4c20e  split uv lock into read/write phases
d20659b96e13e5deca949f5ed96ffc72d6fad043  validate two-phase uv lock bootstrap
328e7054c3adfec96810fec370620a22bd4b2ef7  scope uv lock write permission to commit job
e76680831a16fef5bfc6a56ae5cad95d611fc6b6  dispatch registry policy
71d395af052157a199c4c1c57fe5a459cc7eb7a2  dispatch registry validator
8b26d356b6b3877d84ff56d60eb03143e5faccf7  bind registry to release Action-pin contract
```

Default-branch bootstrap commits include:

```text
953088c4f0361c9b1a7a609ce0b6258d16d0d6cc  canonical uv-lock bootstrap
a6fa36fbc36c57aafc68babc79dcaac139f0cf41  runtime image build registry
5a8c5d8317317bb15dee433157ddacf7a6604c4e  final package registry
e0843f4d1ea9b0a0a580b96af4a3ef70c3f6fcc9  branch protection registry
e7e65029e011c602c3fa907d90702c0692d7ac4e  staging acceptance registry
6aac6d014f9adaf12bce9165314dbccab2d2e71c  production deploy registry
cef48399daa6b07d7015473286b78b0c2a4a07e1  final acceptance registry
3b991cd0eaa114de25ff0609a9c83d2a26832fe3  runtime closure registry
fbe3bdf1efb29abb2bbf76c149dfbc3903a490dd  production IaC registry / audited main snapshot
```

## 7. What is now closed

Closed at source/repository configuration level:

```text
workflow_dispatch default-branch discoverability for all nine release-critical workflow paths
canonical uv-lock default-branch bootstrap availability
resolver/write-token privilege separation for uv-lock regeneration
release-critical dispatch registry drift detection against Action-pin policy
```

## 8. What is not closed

Still blocked:

```text
actual hosted execution of the uv-lock workflow
actual uv lock output
actual uv lock --check PASS
actual uv sync --all-packages --frozen PASS
actual release source tests after lock regeneration
GitHub-hosted runner/account/scheduling execution recovery
remaining PostgreSQL/runtime/image/Staging/Production/DR evidence
strong branch protection applied live
real human approvals
Final Decision accepted=true
```

No hosted workflow was rerun while the established zero-step failure pattern remains.

# KEEP NODE-73 FINAL ACCEPTANCE BLOCKED
