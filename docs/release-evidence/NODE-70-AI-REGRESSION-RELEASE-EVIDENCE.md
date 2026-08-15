# NODE-70 — AI Regression, Experiment & Release Gate — Release Evidence

> Evidence date: 2026-08-15  
> Branch: `node-70-ai-regression-release`  
> Status: **SOURCE IMPLEMENTED / RELEASE BLOCKED**

## Decision

NODE-70 now has a versioned, fail-closed AI release-control source baseline. This is **not** evidence that an AI candidate is approved for production. The repository does not yet contain a real immutable production baseline manifest plus complete candidate runtime evidence, human evaluation, shadow/canary observations, and Staging alias rollback proof.

## Implemented source baseline

- Existing NODE-05 deterministic benchmark harness reused rather than duplicated.
- `ReleaseManifest` pins exact Git SHA, Agent, prompt hash, Skills, Recipe, routing policy, Critic, Constraint policy, Context policy, suite versions, and benchmark profile.
- Floating release identities (`latest`, `main`, `dev`, `unknown`, `*`) are rejected.
- Deterministic release fingerprints and decision IDs.
- Blocking executable suites: `smoke`, `auto-repair`, `visual-critic`.
- Per-case critical guardrails prevent an aggregate score from hiding one critical failure.
- Zero-tolerance critical metrics include safety/constraint failures and unsafe paid/repair side effects where those metrics are present.
- Production `release` mode rejects fixture evidence.
- Supplemental evidence contract for product parity, model/provider benchmark, security Agent red-team, blind human visual pairwise, shadow, canary, and rollback drill.
- Statistical supplemental evidence requires policy minimum sample size and a named confidence method.
- `evals/statistics.py` records sample summaries and Wilson 95% intervals without automatically claiming significance.
- Shadow contract disables external side effects, destructive tools, and user-visible candidate output, and requires authorized data plus explicit budget.
- Canary state machine: `internal -> 5 -> 25 -> 50 -> 100`.
- Automatic canary rollback decision for provider failure, critical failure, gate regression, error/cost regression, or quality regression.
- Rollback contract restores the exact baseline alias.
- Live provider preflight is disabled by default and requires API key, positive budget, exact suite ACK, no-side-effect mode, and budget ceiling.
- `scripts/ai-release-gate.py` emits an archival release decision JSON from real manifests/run reports/evidence.
- `reports/ai-releases/` archive contract added.
- `AI Regression Release Gate` workflow added with dependency-free source contract, frozen canonical tests, and manual-only live preflight.

## Existing eval assets reused

The repository already contains executable benchmark suites and deterministic fixture machinery from NODE-05. NODE-70 treats `product-parity` and `model-provider` as supplemental evidence because their current suite files are specification/benchmark definitions rather than the executable `SuiteDefinition + v1 cases` contract consumed by `run_suite()`.

This distinction prevents a specification-only dataset from being falsely reported as an executed green suite.

## Direct source contract expectations

`python3 scripts/validate_ai_release_contract.py` must prove all of the following once CI can execute:

- the required executable suites can be loaded and contain cases;
- a clean fixture comparison passes contract mode;
- one critical case failure blocks even when aggregate critical score is left unchanged;
- fixture evidence cannot pass production release mode;
- shadow is side-effect free;
- canary can advance only inside guardrails;
- rollback restores baseline alias;
- live provider evaluation is SKIPPED by default.

## Release blockers

- [ ] NODE-70 `source-contract` actually executes on a GitHub runner.
- [ ] Frozen `canonical-eval-tests` execute and pass.
- [ ] Root `uv.lock` freshness blocker inherited from NODE-66 is resolved.
- [ ] Exact current production baseline manifest is captured from a real deployed production configuration.
- [ ] Candidate manifest is captured from the exact candidate build/configuration.
- [ ] Baseline and candidate reports exist for `smoke`, `auto-repair`, and `visual-critic` using the exact pinned versions.
- [ ] Product parity acceptance evidence is executed and reviewed.
- [ ] Model/provider benchmark is executed under explicit budget and has sufficient statistical evidence.
- [ ] Agent security red-team evidence passes with zero critical failure.
- [ ] Blind human pairwise visual evaluation is complete with sufficient sample size/confidence method.
- [ ] Shadow run is executed on authorized data with no candidate side effects.
- [ ] Canary stages are exercised with monitored quality/error/cost signals.
- [ ] Staging rollback drill proves production alias/configuration can return to baseline without a full-service redeploy where applicable.
- [ ] Running Agent Runs remain on their exact frozen versions during alias changes.
- [ ] Final release report is archived under `reports/ai-releases/`.

## Truth rules

1. A fixture is test evidence, never a production baseline.
2. A specification-only dataset is not an executed evaluation.
3. One critical case failure blocks release regardless of aggregate averages.
4. Cost and latency regressions are release dimensions, not optional dashboard information.
5. Small-sample improvement does not become a significance claim automatically.
6. Pull Requests do not automatically spend provider money.
7. Shadow candidate behavior must have zero external side effects.
8. Canary rollout is reversible configuration, not a mutation of already-running frozen Agent versions.
9. A rollback contract is not considered production-ready until the real routing/alias integration is exercised in Staging.
10. A blocked GitHub runner is not a passing or failing AI evaluation; it is missing execution evidence.

## Current status

```text
RELEASE MANIFEST CONTRACT: IMPLEMENTED
PER-CASE CRITICAL GATE: IMPLEMENTED
EXECUTABLE SUITE GATE: IMPLEMENTED
STATISTICAL HELPERS: IMPLEMENTED
SUPPLEMENTAL EVIDENCE CONTRACT: IMPLEMENTED
SHADOW CONTRACT: IMPLEMENTED
CANARY/ROLLBACK STATE MACHINE: IMPLEMENTED
LIVE PROVIDER BUDGET PREFLIGHT: IMPLEMENTED
ARCHIVAL RELEASE CLI: IMPLEMENTED
REAL PRODUCTION BASELINE: MISSING
REAL CANDIDATE RELEASE REPORT: MISSING
HUMAN/SHADOW/CANARY RUNTIME EVIDENCE: MISSING
REAL ALIAS ROLLBACK INTEGRATION TEST: MISSING
NODE-70 RELEASE STATUS: BLOCKED
```

NODE-71 may proceed once this source baseline is preserved, but NODE-70 must not be marked complete until the runtime and Staging evidence above exists.
