# NODE-73 Staging Evidence Artifact Integrity Closure

Status: **SOURCE/CODE-ADDRESSABLE CLOSURE IMPLEMENTED — RUNTIME ACCEPTANCE STILL BLOCKED**

## Scope

This closure addresses a NODE-71/NODE-73 evidence-integrity gap discovered while auditing the real Staging acceptance path.

Before this change, the generic `staging-acceptance-gate.py` logic required a `PASS` scenario to contain fields such as `actual`, `evidence_ref`, and `owner`, but most generic scenario/parity references were not themselves bound to immutable repository bytes or a real producer run. Specialized Media Generation and Tool Gateway validators were already stronger, but generic DB/migration, resilience, browser, performance, data-lifecycle, observability and parity claims could still rely on an arbitrary non-empty `evidence_ref` string.

This report does **not** claim those scenarios have now executed or passed. It records only the source-level closure of that generic evidence-integrity bypass.

## Canonical artifact catalog

`staging/acceptance/evidence-template.json` now contains:

```json
"evidence_artifacts": {}
```

Every `PASS` entry under:

```text
environment_parity
scenario_results
```

must resolve its logical `evidence_ref` through that catalog.

Each catalog entry binds:

```text
logical evidence_ref
repository evidence JSON path
SHA-256 of exact bytes
tested RC git SHA
```

Repository evidence bytes are restricted below:

```text
reports/staging-acceptance/evidence/
```

Path escape and symlink traversal are fail-closed.

## Canonical evidence wrapper

The bound JSON wrapper uses:

```text
schema_version = 1
kind = LUMI_STAGING_EVIDENCE_ARTIFACT_V1
artifact_id = exact logical evidence_ref
status = PASS
rc_git_sha = exact tested RC SHA
captured_at = non-PENDING
```

Producer provenance records:

```text
repository
workflow name
workflow path
run id
run attempt
canonical Actions run URL
producer head SHA
producer head branch
```

The producer head identity intentionally does not have to equal the tested RC SHA. The collector/freeze workflow can run from a later release commit while observing an immutable deployed RC. Tested product identity remains separately bound by `rc_git_sha` plus the NODE-71 runtime-image-set contract.

## Live producer provenance

Canonical validator:

```text
scripts/validate_staging_evidence_artifacts.py
```

The canonical Staging acceptance job runs it with:

```text
--require-live-producers
```

and injects `secrets.GITHUB_TOKEN` only into this acceptance step. The job already owns the narrowly scoped:

```text
contents: read
actions: read
```

permission boundary.

For every unique declared producer run, the validator live-reads GitHub Actions and requires:

```text
repository == zhangjaky71-stack/LUMI-AI-DESIGN-OS
status == completed
conclusion == success
run URL == declared canonical URL
workflow name == declared name
workflow path == declared path
head SHA == declared producer head SHA
head branch == declared producer branch
run attempt == declared attempt
```

A syntactically plausible but nonexistent, failed, unrelated or identity-swapped Actions run therefore cannot satisfy the canonical Staging artifact-integrity gate.

The GitHub Actions workflow-run API shape was checked against a real repository run response while implementing the contract. That API inspection is not acceptance PASS evidence and does not change the hosted-runner blocker.

## Negative drills

The validator self-test covers eight static artifact-binding failures:

```text
missing catalog entry
SHA-256 swap
RC SHA swap
path escape
artifact_id swap
non-PASS wrapper
missing producer workflow-path identity
control-character logical reference
```

It also covers eight live-run identity failures:

```text
run not completed
run conclusion not success
producer head SHA swap
producer head branch swap
run attempt swap
workflow name swap
workflow path swap
repository swap
```

These are source-level negative drills only until GitHub-hosted execution can run them in the trusted workflow.

## Exact workflow snapshot binding

All four NODE-71 code-consuming jobs now use:

```yaml
ref: ${{ github.sha }}
persist-credentials: false
```

for:

```text
source-contract
canonical-lock-gate
remote-read-only-preflight
acceptance-decision
```

This prevents different jobs in one workflow run from silently consuming different `release-closure-p0` revisions if the branch moves while jobs are queued.

## Workflow order

The fail-closed acceptance order is now:

```text
validate evidence path / RC identity
-> bind PASS refs to exact repository evidence bytes
-> live-verify producer Actions runs
-> download exact six-runtime image artifact from requested build run
-> bind Staging evidence to that exact runtime-image set + attestation report
-> run specialized Tool Gateway / Media Generation evidence validators
-> run NODE-71 staging-acceptance decision
-> freeze and self-verify decision provenance
-> archive runtime evidence-artifact binding + decision artifacts
```

Anti-regression contract:

```text
scripts/validate_staging_runtime_image_workflow_contract.py
```

It now requires the generic artifact validator, live producer mode, single scoped token injection, exact-SHA checkouts, execution ordering and runtime report archive path.

## Specialized semantic validation remains mandatory

The generic layer proves artifact-byte integrity, tested-RC binding and producer-run provenance. It does not pretend to infer the semantic truth of every product scenario from arbitrary JSON.

Existing scenario-specific validators remain authoritative where present, including Media Generation and Tool Gateway controls. Other generic scenarios still require their real collector evidence and release/human review before acceptance.

## Key commits

```text
7002d142  add generic staging evidence artifact validator
6072c9ab  add evidence_artifacts to canonical template
a2054296  bind generic artifact validation into Staging workflow
5297a6e2  support canonical URL/path logical evidence refs
a16d77bb  anti-regress generic binding + exact-SHA Staging checkout
03b46b83  add live GitHub Actions producer provenance validation
fa0ddd15  scope live producer token to acceptance-decision
3743c00b  anti-regress live producer verification/trust boundary
8f9cce33  document canonical Staging evidence artifact format
```

## Not claimed

No current runtime PASS is claimed for:

```text
canonical uv.lock / frozen workspace
PostgreSQL migrations or ORM drift
NODE-71 Staging scenarios
browser/performance/resilience evidence
six-runtime build/start/promotion
Staging deployment parity
Production IaC/deployment
branch protection / Evidence Head lock
human approvals
Final Decision
```

The new generic artifact/live-producer gate has not yet executed successfully in GitHub Actions while the repository continues to exhibit the known zero-step hosted execution blocker.

## Verdict

The generic Staging `evidence_ref` free-form integrity bypass is now code-addressably closed and anti-regressed.

NODE-73 remains:

**IMPLEMENTED -> VALIDATING -> BLOCKED_EXTERNAL**

Final release verdict remains:

# KEEP NODE-73 FINAL ACCEPTANCE BLOCKED
