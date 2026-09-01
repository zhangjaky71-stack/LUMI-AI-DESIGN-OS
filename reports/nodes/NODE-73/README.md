# NODE-73 — Final Acceptance Release Closure

## Release posture

NODE-73 Final Acceptance remains **BLOCKED**. PR #135 (`release-closure-p0` → `node-73-final-acceptance-release`) must remain **Draft** and must not be merged until the live staging / production / immutable-evidence chain produces an auditable final `accepted=true` decision.

A green pull-request source workflow is code-addressable evidence only. It is not a substitute for NODE-71 sealed Staging, NODE-72 exact-digest promotion, or NODE-73 dispatch-only Final Acceptance.

## 2026-08-30 source-closure checkpoint

The release-closure branch has completed the current code-addressable repair cycle without weakening acceptance gates.

### Agent Team / Agent Registry

- NODE-37 materialized all 16 canonical `2.0.0` Agent Team candidate definitions (`agent.yaml` + `system.md`) at commit `e80e84cb61884d0536428fc7a76108c147b46205`.
- NODE-30 release metadata now registers the 16 new definitions as `CANDIDATE` with their exact `team-*-v1` eval profiles; existing `production` aliases remain on the previously released 1.x versions.
- Agent Registry revision tests were made revision-relative so they continue to prove monotonic revision increments instead of assuming the original manifest revision forever.

### Final targeted quality validation

`Final Release Quality Repair` run `33297672059`, final repair job `99222709767`, completed **SUCCESS** before its temporary workflow was removed.

That job used a frozen workspace install and passed all of the following before committing the reviewed quality repairs:

- exact Ruff gates for Image Generation, Agent Registry, and Workflow Recipe Engine;
- NODE-46 Image Generation tests and Pyright;
- NODE-30 Agent Registry static contract, tests, and Pyright;
- NODE-32 Workflow Recipe Engine static contract, tests, and Pyright;
- patch sanity (`git diff --check`).

The validated repair payload was committed as `83c19b4060c5cf2ae36b9e2c190a7950fbd4a2b4` (`fix: close final static quality blockers [skip ci]`).

### Other code-addressable closure included in this branch

Targeted hosted repair/validation during this closure cycle also addressed the previously observed shared roots in:

- Queue Event Runtime and the Observability regression fixture;
- Project Integration gateway/protocol typing and approval fixtures;
- Media Dispatch canonical idempotency operation / generation foreign-key identity;
- Audit Governance semantic/type validation;
- Asset Intelligence quality findings;
- MCP Integration Security workspace dependency installation;
- provider-health compatibility and multiple formatter-brittle static validators.

These targeted results are not being used as a substitute for the final canonical PR suite. The purpose of this checkpoint is to record what was repaired before the clean-head formal rerun.

### Temporary repair tooling removed

One-shot release repair workflows and compatibility wrappers used to diagnose and land the fixes have been removed. Canonical workflows and validators remain the source of truth.

## Formal clean-head validation

This documentation update is intentionally a normal, non-`[skip ci]` commit. Its purpose is to trigger the canonical pull-request workflow set after temporary repair tooling has been removed.

The release may not claim source closure until the workflows associated with this clean head complete and all code-addressable release gates required by the PR are green. Any failure on this head is new evidence and must be resolved rather than bypassed.

## Immutable / live acceptance boundary

Even after source CI is green, Final Acceptance remains blocked until the live chain is genuinely proven. Required evidence includes:

- completion of the one-time target AWS account / protected Staging bootstrap tracked by the release handoff;
- reviewed Staging Terraform plan and separately authorized core apply;
- exact frozen six-runtime digest promotion into Staging ECR without rebuild;
- distinct least-privilege migration and application database identities, with the RDS master credential kept outside application runtime use;
- real database parity, Tool Gateway P0, media-generation, private Model Gateway, and canonical image/video runtime evidence;
- approved live provider/model/image/video benchmark evidence;
- workflow-dispatch NODE-71 Staging decision with `passed=true` bound to the exact approved runtime image set;
- Production Terraform plan/apply and NODE-72 promotion of those exact Staging-approved digests without rebuild;
- production smoke, canary, rollback, DR, and recovery evidence;
- frozen V2 Final Acceptance evidence package;
- workflow-dispatch-only NODE-73 final decision with auditable `accepted=true`.

The Security Release Gate / Dependency Review result must also be taken from the final canonical clean head. A historical platform-setting failure or a historical success is not sufficient evidence for the current head.

## Verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**
