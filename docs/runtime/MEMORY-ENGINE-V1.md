# LUMI Memory Engine V1

> NODE-35 — Memory Engine  
> Runtime contract: `MemoryEngine:v1`  
> Depends on: NODE-10 Persistence, NODE-22 Model Gateway embedding authority, NODE-29 Deep Agents Runtime, NODE-34 Context Engine  
> Status: implementation contract; completion still requires executed CI gates

## 1. Purpose

Memory Engine stores **deliberately extracted long-term facts** that should survive across tasks or runs.

It is not:

- a LangGraph checkpoint;
- a replay of raw conversation history;
- a prompt cache;
- a second Project/Brand database;
- a way for an Agent to grant itself broader authority.

The three adjacent persistence concepts are intentionally separate:

```text
Checkpoint
  = where a graph/run can resume

Context Engine
  = what evidence should this model call see now

Memory Engine
  = which durable, governed facts learned across tasks should remain available later
```

## 2. Source-of-truth boundary

Memory is its own durable source only for extracted memory records.

Existing structured systems remain authoritative for their own facts:

- Project brief/settings remain Project-owned;
- Brand hard rules remain BrandRule-owned;
- Task execution state remains TaskGraph-owned;
- Artifact lineage remains Artifact-owned;
- Agent/Skill definitions remain Registry-owned.

When a memory candidate proposes a Brand hard constraint, NODE-35 does **not** silently turn it into a normal active memory. It becomes a `BRAND_RULE_PROPOSAL` for the Brand-owned workflow.

## 3. Scope model

Canonical scopes:

```text
SESSION
USER
PROJECT
BRAND
AGENT
ORGANIZATION
```

Every record has an explicit `scope_type + scope_id`.

Scope is server-derived from trusted invocation/session identity. Model text, Store values, or retrieval queries cannot substitute another organization/project/user/agent scope.

## 4. Memory kinds

Canonical kinds:

```text
PREFERENCE
FACT
DECISION
CONSTRAINT_PREFERENCE
WORKFLOW_LEARNING
EPISODIC_SUMMARY
```

Examples:

- `PREFERENCE`: user tends to prefer spacious layouts;
- `FACT`: a durable project fact not already owned by a stronger structured system;
- `DECISION`: approved direction or decision rationale;
- `CONSTRAINT_PREFERENCE`: a candidate constraint; Brand scope routes to proposal;
- `WORKFLOW_LEARNING`: repeatable execution lesson;
- `EPISODIC_SUMMARY`: compressed outcome of a previous episode/task.

## 5. Record contract

A durable `MemoryRecord` contains:

```text
memory_id
organization_id
scope_type / scope_id
kind
semantic_key
content_structured
summary
source_refs[]
confidence
status
created_by_type / created_by_id
created_at / last_confirmed_at
expires_at
valid_from / valid_to
supersedes_id
version
retention_hold
deleted_at
optional embedding + embedding_model/version
metadata
```

Every source reference includes:

```text
source_type
source_id
version
content_hash
```

A memory without provenance is not a valid production memory.

## 6. Candidate pipeline

All writes pass through the same governed pipeline:

```text
observation
  -> MemoryCandidate
  -> sensitivity classification
  -> tenant / actor / scope validation
  -> Brand proposal decision
  -> semantic-key lookup under concurrency lock
  -> exact dedupe / conflict classification
  -> confidence decision
  -> WRITE | CONFIRM | PROPOSAL | REJECT
```

Agents do not write `memory_records` directly.

## 7. Sensitive-content policy

The general Memory Engine rejects obvious high-risk persistent content such as:

- API keys, bearer tokens, passwords and private keys;
- payment/card/bank identifiers;
- health/medical details;
- SSN/passport/national-ID-shaped identifiers.

For `REJECT_SENSITIVE` and `REJECT_SCOPE`, NODE-35 deliberately does **not** persist the rejected candidate body into `memory_candidates`.

This avoids turning an attempted secret leak into a second durable secret store.

## 8. Actor write authority

### Agent

Allowed by default:

```text
SESSION
PROJECT
AGENT
```

Brand `CONSTRAINT_PREFERENCE` may become `BRAND_RULE_PROPOSAL`.

Denied by default:

```text
USER
ORGANIZATION
normal BRAND writes
```

### User

Allowed by default:

```text
SESSION
USER
PROJECT
```

Brand constraints become proposals.

### System

System operations can write within a trusted server-resolved scope, but still cannot cross organization identity.

## 9. Exact dedupe

Identity for conflict lookup is:

```text
organization
+ scope_type
+ scope_id
+ kind
+ semantic_key
```

If content hash also matches an existing ACTIVE record:

```text
DEDUPLICATE_CONFIRM
```

The existing record is retained, confirmation time/source lineage/confidence are updated, and version increases.

No duplicate ACTIVE row is created.

## 10. Explicit remember

An explicit user/authorized instruction to remember a fact raises candidate confidence to at least `0.9`.

It does not bypass:

- sensitivity policy;
- tenant/scope checks;
- BrandRule ownership;
- retention policy.

## 11. Conflict handling

Same semantic key with different content defaults to:

```text
REQUIRE_CONFIRMATION
```

unless one of two conditions is true:

1. `temporal_coexistence=true` — both facts may be valid for different episodes/times;
2. an explicit high-confidence remember action authorizes replacement.

Replacement behavior:

```text
old ACTIVE -> SUPERSEDED
old.valid_to = now
new ACTIVE.supersedes_id = old.id
```

Lineage remains queryable.

## 12. Concurrency correctness

The PostgreSQL repository serializes same-key decisions with:

```sql
SELECT pg_advisory_xact_lock(hashtextextended(...))
```

then locks any existing ACTIVE rows with:

```sql
FOR UPDATE
```

The advisory lock is important when **no old row exists yet**. Two concurrent writers for the same semantic key cannot both observe an empty set and independently create duplicate ACTIVE facts.

All multi-step production operations execute inside one DB transaction.

## 13. Optimistic versioning

Mutable records use version-CAS:

```text
WHERE id = ... AND version = expected
SET version = version + 1
```

Used for:

- exact confirmation;
- supersede;
- retention/expiry updates;
- soft delete;
- consolidation.

Stale writers fail rather than overwriting a newer memory version.

## 14. Retrieval ordering

Permission/scope filtering happens **before scoring**.

A high-scoring foreign-project memory must never become eligible for ranking.

Reference hybrid score:

```text
0.30 lexical relevance
0.28 semantic similarity
0.20 scope priority
0.14 confidence
0.08 freshness
```

Reference scope weights:

```text
SESSION       1.00
PROJECT       0.98
BRAND         0.90
USER          0.78
AGENT         0.62
ORGANIZATION  0.50
```

These are ranking signals only; they never override permission filtering.

## 15. Embedding authority

Memory records may store an optional pgvector embedding together with:

```text
embedding_model
embedding_version
embedding_dimensions
```

NODE-35 does not call a model provider itself.

Query/candidate embeddings must be produced through an authorized model path such as NODE-22 Model Gateway, then supplied to Memory Engine.

If no compatible embedding exists, retrieval remains deterministic lexical/scope/confidence/freshness search.

## 16. Database schema

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

`memory_candidates` contains extracted structured candidate content only. There is no raw chat/message history column.

Runtime role:

```text
SELECT / INSERT / UPDATE
```

Direct SQL `DELETE` is revoked from `lumi_app`.

Deletion therefore goes through governed soft-delete logic.

## 17. User deletion and retention

Normal delete:

```text
ACTIVE -> DELETED
set deleted_at
increment version
```

`retention_hold=true` blocks deletion until the hold is removed by an authorized governance path.

User-scoped memory is deletable by that user.

Project memory deletion by an Agent/User requires explicit:

```text
memory.project.delete
```

System governance may delete within trusted scope.

## 18. Expiry

Records with expired `expires_at` are excluded from ACTIVE reads.

Consolidation converts eligible expired records to:

```text
EXPIRED
```

without deleting lineage.

## 19. Consolidation

P0 consolidation targets `EPISODIC_SUMMARY` duplicates in the same scope/semantic key.

It:

- selects a survivor;
- merges unique source references;
- marks duplicates `SUPERSEDED`;
- records `consolidated_into` lineage;
- never upgrades an episodic summary into a Brand/System rule.

## 20. NODE-34 Context integration

`MemoryContextSource` implements the NODE-34 `ContextSourcePort` boundary.

Memory enters context only as L4 retrieved evidence.

Authority:

```text
PROJECT / BRAND / ORGANIZATION memory
  -> TRUSTED_PROJECT_DATA
  -> instruction_authority=none

USER / AGENT / SESSION memory
  -> UNTRUSTED_RETRIEVED_DATA
  -> instruction_authority=none
```

Memory never becomes system/developer/Agent instruction solely because it is persistent.

## 21. Deep Agents integration

`DeepAgentMemoryStore` is a real LangGraph `BaseStore` implementation.

It supports the BaseStore batch operation family used by:

- get;
- put;
- delete;
- search;
- list namespaces;
- async equivalents.

The model-visible namespace is intentionally fixed:

```python
("memory",)
```

The true LUMI organization/project/agent/session scope is constructor-trusted and is not encoded in model-controlled namespace strings.

A different namespace fails with:

```text
MEMORY_STORE_NAMESPACE_DENIED
```

`PutOp` is not a direct DB write. It constructs a `MemoryCandidate` and reruns the full NODE-35 policy pipeline.

## 22. NODE-29 provider boundary

`DeepAgentMemoryStoreProvider` implements the existing NODE-29 store-provider boundary:

```text
store_for_run(context)
```

It derives the project memory store from `DeepAgentInvocationContext`:

- organization;
- project;
- actor;
- root agent;
- run/session;
- granted permissions.

This keeps provider/model text from manufacturing a different scope.

## 23. Memory evaluation suite

NODE-35 also contains a regression framework under:

```text
apps/agent-runtime/src/lumi_agent_runtime/context_eval/
```

Canonical corpus:

```text
evals/context/memory-retrieval-v1.json
```

Eight release cases:

1. required-source recall;
2. compressed fact retention;
3. cross-project isolation;
4. prompt-injection containment;
5. hard token budget;
6. latest-source freshness;
7. distractor resilience;
8. provenance completeness.

The suite evaluates the Memory→Context behavior rather than only individual Memory functions.

## 24. Approved baseline

Baseline:

```text
evals/context/memory-retrieval-baseline-v1.json
```

Regression comparison blocks release on unapproved drops in:

- required source recall;
- fact recall;
- provenance coverage;
- case pass rate.

Security/budget/freshness violation budgets are zero in P0.

## 25. Machine-readable report

Runner:

```text
scripts/run_context_eval_report.py
```

Output schema:

```text
lumi.context-eval-report.v1
```

Default artifact:

```text
artifacts/context-eval/memory-retrieval-v1.json
```

The report includes per-case reasons/metrics, aggregate metrics, pass rate and determinism evidence.

## 26. Determinism gate

Each canonical evaluation case is executed twice.

Release checks compare:

- manifest hash;
- rendered Context hash.

This catches unstable tie ordering, random selection and cache/source-version drift.

## 27. PostgreSQL acceptance

`scripts/integration_memory_engine.py` validates:

- seeded organization/project access;
- two concurrent writers for one new key;
- exactly one ACTIVE record;
- `WRITE + DEDUPLICATE_CONFIRM` outcome pair;
- confirmation increments version;
- conflict requires confirmation;
- explicit replacement supersedes prior record;
- scope-filtered search;
- governed soft delete;
- vector storage/dimension metadata;
- candidate outcomes;
- runtime role cannot SQL DELETE memory.

## 28. Security invariants

Release-blocking invariants:

1. Memory is not checkpoint state.
2. Raw conversation history is not the Memory database.
3. Every memory is organization-scoped and provenance-backed.
4. Permission/scope filtering occurs before ranking.
5. Agents cannot write USER/ORGANIZATION global memory by default.
6. Brand hard constraints become proposals.
7. Rejected sensitive/scope-spoofed candidate bodies are not persisted.
8. Same-key concurrent creation is serialized.
9. Conflict replacement preserves supersede lineage.
10. Runtime role cannot physical DELETE memory rows.
11. Context sees memory as data, never new instruction authority.
12. Deep Agent namespace cannot select another tenant/scope.
13. Memory/Context evaluation must not regress below approved baseline.
14. NODE-35 is not COMPLETE until required execution gates actually run green.
