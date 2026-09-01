# NODE-73 Production Environment Governance Closure

Status: **SOURCE IMPLEMENTED — LIVE ENVIRONMENT NOT YET VERIFIED — FINAL ACCEPTANCE BLOCKED**

## Purpose

NODE-73 Final Decision consumes a fine-grained GitHub credential with repository Administration read permission in order to capture strong branch-protection evidence. A workflow-level or ordinary repository-secret boundary is not sufficient for this credential because release-branch workflow source is still reviewable code.

This closure adds a production-environment trust boundary and live environment-governance verification.

## Source controls implemented

### Final Decision secret boundary

`.github/workflows/final-acceptance-gate.yml` now requires:

```text
final-decision:
  environment: production
  permissions:
    contents: read
    actions: read
    pull-requests: read
```

`RELEASE_GOVERNANCE_TOKEN` is injected only inside the environment-gated Final Decision step. It is not workflow-scoped and is not available to source-contract or canonical-lock-gate.

The ephemeral `GITHUB_TOKEN` is used as `RELEASE_APPROVAL_TOKEN`; `actions: read` is scoped only to Final Decision so it can read production-environment metadata in private-repository-compatible mode.

### Canonical environment policy

`final/acceptance/release-environment-policy-template.json` requires:

```text
environment = production
minimum_required_reviewers >= 1
prevent_self_review = true
deployment_branch_policy.protected_branches = true
deployment_branch_policy.custom_branch_policies = false
```

### Live verifier

`scripts/validate_live_release_environment_v1.py` reads the GitHub production environment and fail-closes unless the live configuration satisfies the canonical policy.

It records only normalized reviewer identities (`user:<login>` / `team:<slug>`) and policy state.

### Final Decision binding

`scripts/final-acceptance-decision-v2.py` now writes:

```text
reports/final-acceptance/<release-id>/runtime-v2/production-environment-live.json
```

The runtime report is hash-bound into `live_release_controls.production_environment` and the committed environment policy is hash-bound into `canonical_inputs.release_environment_policy`.

### Anti-regression

`validate_release_workflow_permissions.py` requires Actions/PR read permissions to remain scoped to Final Decision and blocks write/OIDC/package/attestation expansion.

`validate_finalization_v2_contract.py` runs the environment verifier self-test, validates the committed policy, requires the Final Decision markers, requires the production environment boundary, and binds the secret location.

## GitHub platform semantics verified

GitHub documents that environment protection rules can require reviewers, prevent self-review, and restrict deployment to protected branches. Environment secrets are not made available until configured protection rules pass. The environment REST API exposes protection rules and deployment branch policy and can be read with Actions repository permission (read).

## Not claimed

No live production-environment PASS is claimed here.

The current connector cannot inspect the repository environment endpoint, and GitHub-hosted Actions continue to fail before executable steps. Therefore the following remain external/runtime requirements:

```text
production environment actually exists
required reviewers are actually configured
prevent self-review is actually enabled
protected-branches deployment policy is actually enabled
RELEASE_GOVERNANCE_TOKEN exists as a production environment secret with Administration read
production environment review is completed by an authorized reviewer
Final Decision successfully captures production-environment-live.json
```

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**
