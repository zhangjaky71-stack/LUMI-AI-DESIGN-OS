# NODE-31 — Acceptance Evidence

Status: **IMPLEMENTED → VALIDATING → BLOCKED_EXTERNAL**

NODE-31 implements immutable Skill publication, dependency/evaluation gates, exact runtime resolution, package materialization, and the NODE-29 `SkillMaterializer` contract.

## Implemented

- `SkillScope`, `SkillFile`, `SkillManifest`, `PublishedSkill`, and `SkillEvaluationEvidence` contracts.
- Mandatory `SKILL.md` with traversal-safe UTF-8 package files.
- Exact dependency refs and dependency-hash-bound runtime content identity.
- Self-cycle / corrupted dependency DAG rejection.
- Threshold evaluation gate with policy, subject-hash, status, and score checks.
- Immutable exact-version publication and idempotent same-content republish.
- Project → organization → global resolution with cross-tenant denial.
- Inherited exact-version anti-shadow invariant.
- Direct NODE-29 `SkillMaterializer.materialize(...)` compatibility.
- Runtime checks for Tool Gateway names, sandbox execute, memory read, and memory write requirements.
- Transitive dependency embedding beneath `.lumi/dependencies/...` without returning extra `MaterializedSkill` objects.
- In-memory stores/sinks for deterministic tests.
- Git-workspace canonical JSON store with atomic writes.
- Atomic directory package sink with immutable content-hash marker.

## Authored deterministic tests

`apps/agent-runtime/tests/test_skill_registry_node31.py` covers:

1. immutable exact versions and idempotent republish;
2. stale eval subject rejection and minimum-score gate;
3. dependency hashes participating in runtime content identity;
4. dependency-cycle rejection and inherited exact anti-shadow;
5. cross-tenant project visibility denial;
6. top-level-only materializer output with embedded transitive dependency files;
7. sandbox permission denial;
8. Git store and atomic directory sink round-trip.

## Local evidence

Before Git publication, the NODE-31 source set passed Python syntax compilation. An isolated contract harness exercising the publication/materialization semantics passed **7/7** scenarios.

This local evidence is not a substitute for hosted repository CI.

## Hosted evidence policy

A dedicated `.github/workflows/node-31-skill-registry.yml` runs Ruff and the NODE-31 pytest file.

The repository's preceding NODE-30 push workflow received `runner_id=0` with `steps=[]`, matching the existing external GitHub runner/payment allocation problem. NODE-31 must therefore remain `BLOCKED_EXTERNAL` unless a hosted runner actually executes steps.

## Remaining production composition

- Deployment must mount/sync the protected Git Skill Registry workspace.
- NODE-21/NODE-29 backend composition must map the trusted materialization staging root into virtual `/skills`.
- Benchmark/evaluation infrastructure must produce signed/durable evidence refs consumed by the implemented gate.
- Agent Registry publication should eventually perform cross-registry preflight so a new Agent cannot be promoted with nonexistent Skill refs.

## Next node

**NODE-32 — Context Compiler V1**.
