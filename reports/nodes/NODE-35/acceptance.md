# NODE-35 — Memory Engine Acceptance

> Development branch: `node-35-memory-retrieval-eval`  
> Intended stacked base: `node-34-context-engine-release`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Completion rule: contract, quality and PostgreSQL gates must actually execute green.

## 1. Canonical scope correction

The canonical repository specification is:

```text
docs/nodes/NODE-35-MEMORY-ENGINE.md
```

NODE-35 is **Memory Engine**, not only a retrieval benchmark.

The early Memory/Retrieval evaluation work has been retained as the node's regression/acceptance layer, while the actual Memory Engine runtime, persistence, governance and Deep Agents integration are implemented in this node.

## 2. Runtime delivered

Package:

```text
apps/agent-runtime/src/lumi_agent_runtime/memory_engine/
```

Delivered modules:

- `contracts.py`
- `policy.py`
- `sensitivity.py`
- `repository.py`
- `postgres_repository.py`
- `pipeline.py`
- `retrieval.py`
- `governance.py`
- `service.py`
- `context_source.py`
- `deep_adapter.py`
- `deep_provider.py`
- `errors.py`
- public `__init__.py`

## 3. Memory vs checkpoint

NODE-35 keeps three concepts separate:

```text
LangGraph checkpoint
  -> run resumability/state

NODE-34 Context Engine
  -> evidence selected for this call

NODE-35 Memory Engine
  -> governed long-term learned facts across tasks/runs
```

No raw conversation replay is used as the long-term memory database.

## 4. Scope contract

Implemented exact scope vocabulary:

```text
SESSION
USER
PROJECT
BRAND
AGENT
ORGANIZATION
```

Each record is keyed by explicit organization/scope identity.

`MemoryAccessContext` carries server-trusted scope IDs and granted permissions.

## 5. Kind contract

Implemented:

```text
PREFERENCE
FACT
DECISION
CONSTRAINT_PREFERENCE
WORKFLOW_LEARNING
EPISODIC_SUMMARY
```

## 6. Provenance contract

Every candidate/record requires `MemorySourceRef` containing:

```text
source_type
source_id
version
content_hash
```

Version/supersede/consolidation operations preserve source lineage.

## 7. Candidate pipeline

Implemented pipeline:

```text
candidate
-> sensitivity classification
-> organization/actor/scope validation
-> Brand proposal routing
-> same semantic-key lookup
-> exact dedupe / conflict classification
-> confidence decision
-> write / confirm / proposal / reject
```

Agents never write the durable table directly.

## 8. Sensitive-content protection

General Memory rejects obvious:

- credentials/API tokens/private keys;
- payment/bank identifiers;
- health/medical content;
- government-ID-shaped identifiers.

`REJECT_SENSITIVE` and `REJECT_SCOPE` bodies are not persisted to `memory_candidates`.

This invariant is covered by unit and static contract tests.

## 9. Actor authority

Agent default write scope:

```text
SESSION
PROJECT
AGENT
```

Agent cannot write:

```text
USER
ORGANIZATION
normal BRAND memory
```

Brand constraints become `BRAND_RULE_PROPOSAL`.

Project deletion requires explicit `memory.project.delete` for Agent/User.

## 10. Dedupe and explicit remember

Exact same semantic key + content hash:

```text
DEDUPLICATE_CONFIRM
```

No second ACTIVE record is created.

`explicit_remember=true` raises confidence to at least `0.9` but does not bypass sensitivity/scope/Brand ownership.

## 11. Conflict handling

Same semantic key with different content defaults to:

```text
REQUIRE_CONFIRMATION
```

Explicit high-confidence replacement:

```text
old ACTIVE -> SUPERSEDED
new ACTIVE.supersedes_id = old.id
```

`temporal_coexistence=true` permits multiple temporally valid records.

## 12. Concurrency correctness

Production Postgres repository uses transaction-local:

```text
pg_advisory_xact_lock(hashtextextended(...))
```

before same-key lookup plus:

```text
FOR UPDATE
```

This serializes concurrent first writes even when no row exists yet.

Record mutations use version-CAS.

## 13. Retrieval

Permission/scope filtering occurs before ranking.

Hybrid signals:

- lexical relevance;
- semantic cosine when supplied;
- scope priority;
- confidence;
- freshness.

Foreign organization/project memories cannot enter the ranking set.

## 14. Embedding boundary

Memory supports explicit:

```text
embedding
embedding_model
embedding_version
embedding_dimensions
```

No model/provider SDK is imported by Memory Engine.

Embeddings are supplied from an authorized path such as NODE-22.

## 15. Governance

Implemented:

- governed soft delete;
- runtime SQL DELETE denied;
- retention hold;
- expiry to `EXPIRED`;
- episodic consolidation;
- source-ref merge;
- `consolidated_into` lineage;
- superseded history preserved.

## 16. Persistence

Migration:

```text
0016_memory_engine
```

Parent:

```text
0015_task_graph_runtime
```

Tables:

```text
memory_records
memory_candidates
```

ORM:

```text
MemoryRecordModel
MemoryCandidateModel
```

Both are imported into API persistence model registry.

## 17. Runtime DB role

`lumi_app` receives:

```text
SELECT
INSERT
UPDATE
```

and explicit:

```text
REVOKE DELETE
```

on Memory tables.

Physical deletion is not the application memory-deletion API.

## 18. Postgres repository

`PostgresMemoryRepository` is SDK-neutral and uses an injected connection factory.

It contains no direct `asyncpg`, SQLAlchemy or provider SDK import.

JSONB values are explicitly serialized; JSONB/pgvector readback accepts driver-decoded or textual representations.

## 19. NODE-34 integration and trust origin

`MemoryContextSource` contributes Memory as L4 evidence.

**Scope is not sufficient to grant trust.** The adapter requires both a trusted project-like scope and a trusted record origin.

```text
PROJECT / BRAND / ORGANIZATION
+ created_by_type in {USER, SYSTEM}
  -> TRUSTED_PROJECT_DATA
  -> instruction_authority=none

PROJECT / BRAND / ORGANIZATION
+ created_by_type == AGENT
  -> UNTRUSTED_RETRIEVED_DATA
  -> instruction_authority=none

USER / AGENT / SESSION
  -> UNTRUSTED_RETRIEVED_DATA
  -> instruction_authority=none
```

This prevents an Agent from writing Project-scoped model output and having it trust-promote itself on a later turn.

Memory never promotes itself to system/Agent instructions.

## 20. NODE-29 Deep Agents integration

`DeepAgentMemoryStore` is a real LangGraph `BaseStore` implementation.

The model-visible namespace is fixed:

```python
("memory",)
```

Real LUMI organization/project/agent scope is constructor-trusted.

`PutOp` returns to the Memory candidate pipeline rather than directly mutating PostgreSQL.

`DeepAgentMemoryStoreProvider` implements the existing NODE-29 `store_for_run(context)` boundary.

## 21. Unit tests

### `test_memory_engine.py`

Covers:

- six scopes;
- Agent organization-write denial;
- sensitive rejection with no candidate persistence;
- explicit remember confidence;
- exact dedupe;
- conflict confirmation;
- explicit supersede;
- Brand rule proposal;
- tenant isolation;
- user soft delete;
- retention hold;
- expiry/consolidation;
- Agent Project-memory trust-promotion prevention;
- Context adapter data authority;
- actual LangGraph BaseStore adapter and namespace denial.

### `test_memory_postgres_contract.py`

Covers:

- 0016 migration stacking;
- Memory table/schema markers;
- vector support;
- ORM alignment;
- advisory lock;
- row lock;
- version-CAS;
- SDK-neutral Postgres adapter;
- rejected sensitive/scope bodies do not enter candidate persistence.

## 22. PostgreSQL integration

Script:

```text
scripts/integration_memory_engine.py
```

Acceptance flow:

1. verify seeded organization/project;
2. clean deterministic NODE-35 fixture keys;
3. submit two concurrent same-key explicit candidates;
4. require `WRITE + DEDUPLICATE_CONFIRM`;
5. require exactly one ACTIVE row;
6. require version increment;
7. create conflicting value;
8. require `REQUIRE_CONFIRMATION`;
9. explicitly replace and require `SUPERSEDED` old record;
10. search Project scope;
11. soft-delete a record through governance;
12. write/read vector metadata;
13. verify candidate outcomes;
14. prove `lumi_app` direct DELETE raises insufficient privilege;
15. deterministic cleanup.

## 23. Evaluation framework

Package:

```text
apps/agent-runtime/src/lumi_agent_runtime/context_eval/
```

Canonical corpus:

```text
evals/context/memory-retrieval-v1.json
```

Exactly eight categories:

- required source recall;
- compressed fact retention;
- cross-project isolation;
- prompt-injection containment;
- hard token budget;
- freshness;
- distractor resilience;
- provenance completeness.

## 24. Baseline regression gate

Approved baseline:

```text
evals/context/memory-retrieval-baseline-v1.json
```

Regression checks:

- source recall;
- fact recall;
- provenance coverage;
- case pass rate.

P0 security/budget/freshness violation tolerances are zero.

## 25. Determinism

Each canonical case executes twice.

The suite compares:

- Context manifest freeze hash;
- rendered Context hash.

Any nondeterministic case fails the suite.

## 26. Machine-readable report

Runner:

```text
scripts/run_context_eval_report.py
```

Schema:

```text
lumi.context-eval-report.v1
```

Default file:

```text
artifacts/context-eval/memory-retrieval-v1.json
```

CI will upload this file for later dashboard/trace consumption.

## 27. NODE-34 upstream correctness repair

While implementing NODE-35, the stacked NODE-34 release was audited and found to have missing Context modules and stale DB field assumptions.

NODE-34 release was repaired before NODE-35 finalization:

- restored `contracts.py`;
- restored `budget.py`;
- restored `static_source.py`;
- aligned Postgres Context source to actual Project/Brand/Asset/Artifact ORM;
- changed `asset_embeddings.dims` to canonical `dimensions`;
- added explicit `TRUSTED_PROJECT_DATA` authority boundary;
- restored Context Engine and learning unit tests required by its workflow;
- rewrote PostgreSQL Context integration to use actual project brief + NODE-33 TaskGraph;
- repaired NODE-34 static validator and Postgres contract test.

These are upstream corrections, not NODE-35 Memory semantics.

## 28. Static validator

Script:

```text
scripts/validate_memory_engine_contract.py
```

Release-blocking checks include:

- module presence;
- scope/kind vocabulary;
- no raw-chat schema;
- sensitive rejection does not persist bodies;
- scope policy;
- Brand proposal;
- scope-before-score retrieval;
- consolidation/retention;
- advisory lock / FOR UPDATE / CAS;
- Context data-only adapter;
- record-origin trust check;
- fixed Deep Agent namespace;
- 0016 schema/ORM;
- runtime no DELETE;
- PostgreSQL integration markers;
- 8-case eval/report contract.

## 29. CI gates

Expected workflow:

```text
.github/workflows/memory-engine.yml
```

### memory-contract

- compile runtime/tests/scripts/migration/ORM;
- revalidate NODE-34 Context contract;
- validate NODE-35 Memory contract;
- unit tests;
- canonical 8-case evaluation;
- baseline regression.

### memory-quality

- frozen workspace install;
- pytest;
- NODE-35-scoped Ruff/Pyright;
- machine-readable report generation;
- report artifact upload.

### memory-postgres

- start local infrastructure;
- upgrade DB to 0016;
- Alembic ORM drift check;
- deterministic seed;
- NODE-34 Context readback integration;
- NODE-35 concurrent Memory integration;
- downgrade smoke;
- reset infrastructure.

## 30. Submission validation status

At the time this acceptance file is written, final hosted NODE-35 gates have not yet executed green.

Existing repository PRs have repeatedly encountered a GitHub account billing/spending-limit condition before runner allocation. Therefore the existence of CI files is **not** a PASS claim.

Final classification must be derived from actual job steps/runner assignment.

## 31. Acceptance checklist

- [x] Canonical Memory Engine scope corrected.
- [x] Six scopes implemented.
- [x] Six memory kinds implemented.
- [x] Provenance/version record contract implemented.
- [x] Candidate pipeline implemented.
- [x] Sensitive filter implemented.
- [x] Agent/User/System scope policy implemented.
- [x] Brand constraint proposal implemented.
- [x] Exact dedupe implemented.
- [x] Explicit remember confidence implemented.
- [x] Conflict confirmation/supersede implemented.
- [x] Temporal coexistence supported.
- [x] Scope-first hybrid retrieval implemented.
- [x] Optional embedding fields implemented.
- [x] Soft delete and retention hold implemented.
- [x] Expiry/consolidation implemented.
- [x] 0016 migration implemented.
- [x] ORM models/registry implemented.
- [x] Transactional Postgres repository implemented.
- [x] Advisory lock for concurrent first-write implemented.
- [x] NODE-34 MemoryContextSource implemented.
- [x] Agent Project-memory trust promotion prevented.
- [x] NODE-29 DeepAgent BaseStore implemented.
- [x] DeepAgent store provider implemented.
- [x] Unit tests implemented.
- [x] PostgreSQL integration implemented.
- [x] 8-case Memory/Context eval implemented.
- [x] Baseline regression implemented.
- [x] Machine-readable report runner implemented.
- [x] Runtime documentation implemented.
- [x] Static validator implemented.
- [ ] `memory-contract` hosted gate executed green.
- [ ] `memory-quality` hosted gate executed green.
- [ ] `memory-postgres` hosted gate executed green.

## 32. Current classification

Until all required execution gates actually run green:

```text
IMPLEMENTED / VALIDATING / not COMPLETE
```

If the final hosted job is blocked before runner allocation by the known GitHub account condition:

```text
IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE
```

No hosted PASS is claimed without executed steps.
