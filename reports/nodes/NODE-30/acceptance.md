# NODE-30 Acceptance — Agent Registry

> Branch: `node-30-agent-registry`  
> Base: `node-29-deep-agents-runtime`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

## Acceptance matrix

- [x] Git-versioned `agents/<id>/<version>/agent.yaml + system.md`
- [x] required AgentDefinition fields and schema
- [x] deterministic definition/system-prompt hashes
- [x] exact SemVer, `1.x`, caret and tilde selection
- [x] range selectors only choose PRODUCTION
- [x] production alias resolves exact version
- [x] exact DEPRECATED remains available for historical resume
- [x] DRAFT/DISABLED fail closed
- [x] static system-prompt injection/secret lint
- [x] NODE-23 model-policy resolution with registry hash/version evidence
- [x] NODE-25 exact Tool resolution and ToolDefinition hash evidence
- [x] Skill semantic-range resolution through transitional bootstrap catalog
- [x] Context/Budget/Output/Eval dependency validation
- [x] inline Memory policy hashing
- [x] validation + eval required before CANDIDATE → PRODUCTION
- [x] rollback changes alias/status without mutating definitions
- [x] NODE-29 DeepAgentDefinition conversion with provenance hashes
- [x] append-only AgentRun provenance migration
- [x] runtime provenance permissions narrowed to SELECT/INSERT
- [x] replay-safe provenance freeze and conflict detection
- [x] deterministic provenance-store tests
- [x] runtime documentation and dedicated CI authored

## Committed version examples

```text
creative-director@1.0.0  DEPRECATED
creative-director@1.1.0  PRODUCTION
creative-director@1.2.0  CANDIDATE
creative-director@production -> 1.1.0
researcher@1.0.0          PRODUCTION
critic@1.0.0              PRODUCTION
```

## Deterministic tests

```text
apps/agent-runtime/tests/test_agent_registry.py
apps/agent-runtime/tests/test_agent_registry_release.py
apps/agent-runtime/tests/test_agent_registry_provenance_store.py
```

Key assertions include: `creative-director@^1` resolves 1.1.0 rather than candidate 1.2.0; deprecated 1.0.0 resolves by exact version; missing Skill fails validation; dynamic prompt templates fail lint; failed eval cannot promote; rollback preserves definition hash; identical provenance replay is idempotent; different provenance conflicts; tenant/project mismatch blocks persistence.

## Cross-node integration

`scripts/integration_agent_registry.py` composes the real NODE-23 compiled Capability Registry and real NODE-25 P0 Tool Registry, resolves an Agent, freezes exact dependency evidence, and converts it to NODE-29 DeepAgentDefinition.

`scripts/integration_agent_registry_release.py` verifies candidate promotion and rollback without mutating versioned AgentDefinition content.

## PostgreSQL evidence boundary

Migration `0014_agent_registry_provenance` creates the append-only AgentRun provenance table with hash/revision/size constraints and explicitly revokes UPDATE/DELETE from `lumi_app` while granting SELECT/INSERT.

The connector rejected authoring a fixture containing seeded-database mutation/cleanup operations. NODE-30 therefore does **not** claim a live provenance insert acceptance. Store write semantics are covered by deterministic injected-connection tests, while the PostgreSQL CI gate covers real migration, model metadata loading, schema checks that are safe in the repository's DB harness, and downgrade/upgrade smoke. This limitation is explicit rather than hidden.

## Release discipline

`agents/registry.json` is mutable release metadata, not AgentDefinition content. Promotion/rollback create a new manifest revision. Existing AgentRuns retain frozen exact provenance and are not changed by a later production alias move.

## CI

Required jobs:

1. `agent-registry-contract`
2. `agent-registry-quality`
3. `agent-registry-postgres`

If GitHub Actions again shows `steps=[]`, `runner_id=0` and the known billing/spending annotation, status becomes `IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE`.

If a runner starts and a gate fails, that is an engineering defect and must be fixed before COMPLETE.

## Deferred scope

NODE-31 replaces bootstrap Skill resolution with the real Skill Registry. Later Context/Memory nodes replace remaining bootstrap policy catalogs. No parallel permanent registry is claimed.
