# NODE-34 — Context Engine Acceptance

> Branch: `node-34-context-engine`  
> Base: `node-33-task-graph-release`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Completion rule: required contract, quality and PostgreSQL gates must actually execute green.

## 1. Scope delivered

NODE-34 implements a hierarchical, source-traceable Context Engine for long-running design projects without using raw conversation replay as long-term memory.

Implemented scope:

- five context layers L0–L4;
- hard model-input token budgeting with response reserve;
- budget measured on final rendered/safety-wrapped text;
- deterministic compression;
- hybrid lexical/semantic/authority/recency ranking;
- strict organization + project retrieval scope;
- ProjectSummary / Brand / NODE-33 Task / Asset / Artifact source adapter;
- query-embedding consumption without direct provider authority;
- source/version/hash provenance manifest;
- trusted-system vs trusted-project vs untrusted-retrieved authority separation;
- prompt-injection detection and data-boundary rendering;
- process-local content-addressed context cache;
- project/source-version cache invalidation;
- structured user-correction learning boundary;
- composite source wiring;
- deterministic rendering;
- long-project and PostgreSQL integration acceptance definitions;
- dedicated three-stage CI.

## 2. Architectural boundary

Context Engine is a **derived view**. It does not create a second durable memory/fact database.

Durable facts remain owned by:

- ProjectSummary / ProjectBrief / Brand rules;
- Asset / AssetMetadata / AssetEmbedding;
- Artifact / Artifact provenance;
- NODE-33 TaskGraph;
- Agent / Skill registry.

Cache loss is safe because context can be rebuilt from these durable sources.

## 3. Layer contract

Exact layer order:

```text
L0_SYSTEM
L1_PROJECT
L2_AGENT
L3_TASK
L4_RETRIEVED
```

Required upper layers fail closed if their material cannot fit the allocated context budget.

## 4. Provenance contract

Every selected `ContextItem` requires:

```text
source_type
source_id
version
content_hash
```

`ContextManifest` freezes:

- request semantic hash;
- selected source items;
- total/max tokens;
- source-version vector;
- cache key;
- warnings;
- final freeze hash.

This supports later audit of why a model received a particular fact.

## 5. Token-budget evidence

`ContextRequest` separates:

```text
max_input_tokens
response_reserve_tokens
```

Context may consume only:

```text
max_input_tokens - response_reserve_tokens
```

The builder counts final rendered text, including `TRUSTED_PROJECT_DATA` and `UNTRUSTED_RETRIEVED_DATA` wrappers.

Items that do not fit are deterministically compressed or dropped according to priority. Required layers/sources cannot be silently discarded.

## 6. Long-project memory evidence

The design explicitly rejects raw-chat-history replay as the memory strategy.

Stable project knowledge is expected to live in versioned durable structures such as:

- ProjectSummary;
- ProjectBrief;
- BrandRule;
- structured preference;
- Task output;
- Artifact provenance;
- Asset metadata/embedding.

`PostgresProjectContextSource` contains no raw chat/conversation-history query.

## 7. Trust and prompt-injection evidence

Trust levels:

```text
TRUSTED_SYSTEM
TRUSTED_PROJECT
UNTRUSTED_RETRIEVED
```

Authority rules:

- trusted system / resolved Agent instruction may carry instruction authority;
- trusted Project facts are data only;
- retrieved/user Asset evidence has no instruction authority.

Render boundaries:

```text
[TRUSTED_PROJECT_DATA ...]
[UNTRUSTED_RETRIEVED_DATA ...]
```

The safety policy detects common prompt-injection / secret-shaped markers but never promotes suspicious text to higher authority.

## 8. Retrieval evidence

`RetrievalCandidate` supports:

```text
lexical_score
semantic_score
recency_score
authority_score
```

P0 hybrid ranking:

```text
0.38 semantic
+ 0.32 lexical
+ 0.18 authority
+ 0.12 recency
```

Candidates must match both organization and project before ranking.

`retrieval_limit` bounds the candidate set sent to the final budget stage.

## 9. Embedding authority evidence

Context Engine has no provider SDK/model invocation path.

`SemanticContextSearchPort` is the semantic retrieval boundary. `PostgresProjectContextSource` may consume a `query_embedding` supplied by the caller; the embedding itself must be generated through NODE-22 or another authorized model-gateway path.

A static ORM contract test verifies that the pgvector SQL field assumptions match the repository `AssetEmbedding` model before hosted acceptance can pass.

## 10. PostgreSQL source evidence

`PostgresProjectContextSource` is SDK-neutral and read-only.

It reads:

- latest ProjectSummary;
- Brand rules;
- current NODE-33 Task;
- dependency Task outputs;
- Asset / AssetMetadata candidates;
- Artifact records;
- AssetEmbedding candidates when query embedding is supplied.

Queries are organization/project scoped.

The adapter contains no INSERT / UPDATE / DELETE statements and imports no asyncpg/SQLAlchemy/provider SDK.

## 11. Cache evidence

`InMemoryContextCache` is bounded and process-local.

Cache identity includes exact source versions/hashes, so changing durable source version changes the cache key.

`ContextCacheInvalidator` invalidates project cache for Project/Brand/Asset/Artifact/Task change events.

A future distributed cache may implement the same contract; cache correctness is never business-state correctness.

## 12. Structured correction learning

`CorrectionSignal` supports:

```text
PROJECT_SUMMARY
BRAND_RULE
STRUCTURED_PREFERENCE
```

`ContextFeedbackLearner` creates a `LearningProposal` and submits it through `ProjectLearningPort`.

Context Engine does not write raw chats into long-term memory and does not directly mutate Project-owned facts.

## 13. Unit-test assets

### `test_context_engine.py`

Covers:

- stable layer ordering;
- hard token budget;
- cross-project retrieval rejection;
- prompt-injection detection;
- untrusted authority isolation;
- rendered provenance hash;
- large-summary compression;
- required-source fail-closed behavior;
- cache-key change on source-version change.

### `test_context_learning.py`

Covers:

- structured correction through Project-owned write port;
- absence of raw-chat field;
- project cache invalidation;
- irrelevant-event no-op.

### `test_context_postgres_contract.py`

Covers:

- SDK-neutral/read-only Postgres adapter;
- tenant/project-scoped SQL;
- ProjectSummary/Brand/Task/Asset/Artifact/Embedding reads;
- absence of chat-history source;
- AssetEmbedding ORM field compatibility;
- ProjectSummary model field compatibility.

## 14. Integration assets

### Long-project deterministic integration

`scripts/integration_context_engine.py`

Simulates:

- a very large current ProjectSummary;
- 200 historical retrieval candidates;
- four strongly relevant candidates;
- hard 1,500-token context budget after response reserve;
- maximum 12 retrieval candidates.

Acceptance requires:

- total context <= budget;
- L4 count <= 12 and far below the full 200-item history;
- all four known relevant references survive ranking;
- ProjectSummary is compressed;
- current logo constraint survives compression;
- trusted-project and untrusted-retrieved render boundaries are present.

### PostgreSQL integration

`scripts/integration_context_postgres.py`

Uses deterministic seeded organization/project IDs and:

1. inserts a versioned ProjectSummary;
2. inserts an AgentRun;
3. compiles real NODE-32 `quick-image@production`;
4. instantiates and installs a real NODE-33 TaskGraph;
5. composes Static L0/L2 + PostgreSQL L1/L3/L4 sources;
6. builds the ContextManifest;
7. verifies budget, layer order, ProjectSummary/Task provenance and project-data rendering;
8. cleans generated database state.

## 15. Static validator

`scripts/validate_context_engine_contract.py`

Release-blocking checks include:

- required Context Engine modules physically exist;
- exact L0–L4 vocabulary;
- hard budget and required-source markers;
- project/untrusted authority boundaries;
- hybrid ranking and tenant scope;
- PostgreSQL durable source coverage;
- read-only Postgres adapter;
- no raw chat history source;
- cache/source-version invalidation;
- structured correction learning;
- no ambient DB/provider/network/tool SDK imports in Context Engine runtime.

## 16. Runtime documentation

`docs/runtime/CONTEXT-ENGINE-V1.md`

documents:

- derived-view architecture;
- L0–L4 hierarchy;
- token and response reserve policy;
- compression;
- trust vs instruction authority;
- hybrid retrieval;
- embedding authority boundary;
- Project/Task/Asset/Artifact source paths;
- cache/invalidation;
- structured correction learning;
- long-project behavior;
- release invariants.

## 17. CI gates

Workflow:

`.github/workflows/context-engine.yml`

### `context-contract`

- compile NODE-34 runtime/tests/integrations;
- revalidate NODE-33 TaskGraph static contract;
- run NODE-34 static validator;
- run dependency-light Context tests;
- run long-project deterministic integration.

### `context-quality`

- frozen workspace install;
- pytest;
- Ruff;
- Pyright.

### `context-postgres`

- start repository Postgres infrastructure;
- migrate to current inherited TaskGraph head;
- Alembic metadata drift check;
- deterministic seed;
- real ProjectSummary + NODE-33 TaskGraph context readback integration;
- infrastructure reset.

## 18. Validation status at submission

The final NODE-34 release branch has not yet received a successful hosted runner execution at the time this acceptance file was written.

Previous nodes currently have a GitHub account billing/spending-limit runner-allocation blocker. Therefore no hosted PASS is inferred from the existence of workflow definitions.

The final PR must inspect actual job steps/runner assignment. If `steps=[]` and `runner_id=0` with the known billing annotation, NODE-34 must be classified `BLOCKED_EXTERNAL`, not test failure and not COMPLETE.

## 19. Acceptance checklist

- [x] L0–L4 Context contract implemented.
- [x] Hard total + layer token budget implemented.
- [x] Final rendered wrappers count against budget.
- [x] Required layer/source fail-closed behavior implemented.
- [x] Deterministic compression implemented.
- [x] Hybrid lexical/semantic retrieval contract implemented.
- [x] Organization/project retrieval scope enforced.
- [x] Source ID/version/hash provenance implemented.
- [x] Project facts separated from instruction authority.
- [x] Retrieved/user data rendered as untrusted.
- [x] Raw chat excluded as long-term memory source.
- [x] ProjectSummary/Brand/Task/Asset/Artifact source adapter implemented.
- [x] Semantic query embedding does not bypass NODE-22 authority.
- [x] Version-keyed replaceable cache implemented.
- [x] Project event invalidation implemented.
- [x] Structured correction learning boundary implemented.
- [x] Long-project integration asset implemented.
- [x] PostgreSQL Context readback integration asset implemented.
- [x] Static validator implemented.
- [x] Runtime documentation implemented.
- [x] Dedicated three-stage CI implemented.
- [ ] `context-contract` hosted gate executed green.
- [ ] `context-quality` hosted gate executed green.
- [ ] `context-postgres` hosted gate executed green.

## 20. Current classification

Until required execution gates actually run green:

```text
IMPLEMENTED
VALIDATING
not COMPLETE
```

If the hosted job is blocked before runner allocation by the known GitHub billing/spending-limit condition:

```text
IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE
```

No hosted PASS is claimed without executed steps.
