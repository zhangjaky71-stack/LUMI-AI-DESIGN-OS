# LUMI Context Engine V1

> NODE-34 — Context Engine  
> Phase 4 Agent Intelligence  
> Depends on NODE-16 Project Core, NODE-18 Asset Storage, NODE-22 Model Gateway, NODE-30/31 Agent & Skill Registry, NODE-33 Task Graph  
> Next: NODE-35 Memory / Retrieval Evaluation

## 1. Purpose

Context Engine builds the smallest useful, source-traceable model context for one Agent Task.

It is a **derived-view system**, not a new source-of-truth database. Durable facts remain owned by:

- ProjectSummary / ProjectBrief / Brand rules;
- Assets and AssetMetadata/AssetEmbedding;
- Artifacts and Artifact provenance;
- NODE-33 Tasks and Task outputs;
- Agent/Skill registries.

Context Engine selects, ranks, compresses and renders those facts under a hard input-token budget.

It must never solve long-project memory by replaying the entire conversation history.

## 2. Five-layer context model

Context is assembled in fixed semantic layers:

```text
L0_SYSTEM     system/runtime policy and safety boundaries
L1_PROJECT    ProjectSummary, Brand rules and stable project facts
L2_AGENT      resolved Agent/Skill instruction context
L3_TASK       current Task input and relevant dependency outputs
L4_RETRIEVED  retrieved Asset / Artifact / Research / Feedback evidence
```

Layer order is stable. Budget allocation may shrink lower-priority material, but required upper layers fail closed if they cannot fit.

## 3. ContextRequest

A request freezes:

```text
organization_id
project_id
agent_run_id
task_id
agent_ref
purpose
query
max_input_tokens
response_reserve_tokens
layer_budgets
required_source_ids
retrieval_limit
```

`context_budget_tokens` is:

```text
max_input_tokens - response_reserve_tokens
```

The response reserve is never consumed by context assembly.

## 4. Source provenance

Every `ContextItem` has a required `ContextSourceRef`:

```text
source_type
source_id
version
content_hash
```

The final `ContextManifest` stores:

- request semantic hash;
- exact selected items;
- total token estimate;
- source-version vector;
- content-addressed cache key;
- warnings;
- deterministic manifest freeze hash.

This makes it possible to answer "why did the Agent know this?" without reverse-engineering a prompt string.

## 5. No raw-history memory strategy

Long project state must be promoted into durable facts such as:

- `ProjectSummary`;
- ProjectBrief versions;
- Brand rules;
- structured preferences;
- Artifact versions/provenance;
- Task outputs;
- Asset metadata and embeddings.

The PostgreSQL Context adapter contains no query for raw chat history or conversation message tables.

Old chat is not automatically authoritative. Stable corrections are promoted through a structured learning boundary instead.

## 6. Token budget policy

The P0 default estimator is deliberately conservative and dependency-free. Production callers may inject the exact tokenizer for the selected NODE-22 model.

Budget is enforced twice:

1. per-layer caps;
2. total context budget.

The budget is measured against the **final rendered form**, including safety/data-boundary wrappers. Untrusted-data delimiters do not get free tokens.

If an item does not fit:

- deterministic compression is attempted;
- lower-priority material may be dropped;
- a required layer/source may not be silently dropped;
- required content that cannot fit raises a budget error.

## 7. Compression

P0 compression is deterministic/extractive and does not call a model.

It:

- keeps the earliest bounded sentence set that fits;
- falls back to bounded clipping only when necessary;
- records `compressed=true` and original token estimate;
- leaves individual Brand rules/structured facts as separate high-priority items so critical constraints do not disappear inside a giant summary.

A later summarization model may be added behind the same contract, but it must use NODE-22 and preserve source provenance.

## 8. Trust and instruction authority

Trust is not the same thing as instruction authority.

### TRUSTED_SYSTEM

L0/L2 system and resolved Agent instruction can carry instruction authority.

### TRUSTED_PROJECT

ProjectSummary, Task output and Artifact facts are trusted project **data**, not system instruction. They render inside:

```text
[TRUSTED_PROJECT_DATA ...]
...
[/TRUSTED_PROJECT_DATA]
```

### UNTRUSTED_RETRIEVED

User-uploaded/retrieved Assets and external evidence have no instruction authority and render inside:

```text
[UNTRUSTED_RETRIEVED_DATA ...]
...
[/UNTRUSTED_RETRIEVED_DATA]
```

The safety inspector detects markers such as:

- ignore previous instructions;
- reveal system prompt;
- role-tag injection;
- bearer/API-key shaped text.

Detection does not promote the content. Suspicious text remains data with `instruction_authority=none`.

## 9. Tenant and project scope

Retrieval candidates must match both:

```text
organization_id
project_id
```

Candidates from another Project are discarded before ranking, even if their semantic/lexical score is higher.

PostgreSQL source queries are organization/project scoped.

## 10. Hybrid retrieval

`RetrievalCandidate` carries bounded normalized scores:

```text
lexical_score
semantic_score
recency_score
authority_score
```

P0 hybrid score:

```text
0.38 semantic
+ 0.32 lexical
+ 0.18 authority
+ 0.12 recency
```

Results are scope-filtered, ranked and deduplicated by source identity/version before the token-budget pass.

## 11. Embedding authority boundary

Context Engine does not invoke embedding/model providers directly.

If semantic retrieval is requested, the caller supplies `query_embedding` produced through the NODE-22 Model Gateway. The Project source may consume that vector for pgvector search; it never owns an API key or provider SDK.

`SemanticContextSearchPort` also exists as a boundary for moving semantic search to a dedicated retrieval service without changing the builder.

## 12. PostgreSQL durable source

`PostgresProjectContextSource` is read-only and SDK-neutral. It uses an injected connection protocol.

It can load:

### L1

- latest ProjectSummary;
- Brand rules linked through Project/Brand.

### L3

- current NODE-33 Task;
- direct dependency Task outputs.

### L4

- lexical Asset/AssetMetadata candidates;
- semantic AssetEmbedding candidates when a query vector is supplied;
- related Artifact records.

It performs no INSERT/UPDATE/DELETE and imports no asyncpg/SQLAlchemy/provider SDK.

## 13. Asset and Artifact handling

Asset text/metadata is rendered as untrusted retrieved data because user-provided files may contain prompt injection.

Artifact facts are project data and retain Artifact identity/version in ContextSourceRef.

Context Engine does not copy Asset binaries into prompts. Binary/image inputs remain Asset references and are passed through the appropriate model/tool contract when required.

## 14. TaskGraph integration

L3 reads the current durable NODE-33 Task and direct dependency outputs.

This means an Agent restarting after process loss can reconstruct Task context from PostgreSQL rather than relying on a previous in-memory conversation.

TaskGraph remains the execution ledger; Context Engine may read it but may not rewrite Task history.

## 15. Agent/Skill integration

`StaticContextSource` converts resolved runtime policy and the exact Agent instruction into L0/L2 source-traceable items.

Production wiring should use the exact NODE-30/NODE-31 resolved versions already frozen for the Agent run. Context Engine must not independently resolve a moving Agent/Skill alias.

## 16. Composite sources

`CompositeContextSource` combines independent sources without merging their authority boundaries.

Typical runtime composition:

```text
StaticContextSource(resolved system + Agent)
+ PostgresProjectContextSource(Project/Task/Asset/Artifact)
+ optional dedicated retrieval source
```

## 17. Cache

`InMemoryContextCache` is process-local and bounded. It stores only derived manifests.

Cache identity includes:

```text
request semantic hash
+ exact source-version vector
```

A source-version change therefore changes the cache key.

Cache loss is safe: durable facts remain in Project/Asset/Artifact/Task systems and the context can be rebuilt.

## 18. Cache invalidation

`ContextCacheInvalidator` conservatively invalidates a Project cache on events such as:

```text
project.summary.updated
project.brief.updated
brand.rule.updated
asset.ready
asset.metadata.updated
artifact.version.created
task.succeeded
task.failed
task.cancelled
```

A future distributed Redis cache can implement the same contract. Cache consistency must never become business correctness authority.

## 19. Feedback learning

User correction is not stored as raw conversation history.

`CorrectionSignal` is an explicit structured signal containing:

```text
organization_id
project_id
target
key
corrected_value
source_ref
confidence
```

Targets:

```text
PROJECT_SUMMARY
BRAND_RULE
STRUCTURED_PREFERENCE
```

`ContextFeedbackLearner` converts the signal to a `LearningProposal` and submits it through `ProjectLearningPort`.

The Project domain remains the owner that validates/writes the new durable fact/version.

## 20. Rendering

`render_manifest()` emits context in stable layer order and returns:

```text
text
manifest_hash
total_tokens
source_versions
```

Project and untrusted data are visibly delimited. Rendering does not discard provenance from the manifest.

## 21. Long-project behavior

The deterministic integration simulates:

- a large ProjectSummary;
- 200 historical retrieval candidates;
- a fixed 1,500-token context budget after response reserve;
- only 12 retrieval candidates eligible for the final ranking stage.

Acceptance requires that:

- summary is compressed;
- critical current-project facts remain;
- irrelevant historical candidate 199 is not included;
- L4 count is bounded;
- final rendered token estimate remains within budget.

## 22. Security boundary

The Context Engine package imports no ambient execution authority such as:

- asyncpg/SQLAlchemy/psycopg;
- provider SDKs;
- requests/browser networking;
- Docker/subprocess.

It receives trusted ports and data. It does not become a new tool/model/database-credential surface inside Agent code.

## 23. Validation gates

### context-contract

- compile all NODE-34 runtime/tests/integrations;
- revalidate NODE-33 TaskGraph contract;
- static Context contract;
- dependency-light unit tests;
- long-project deterministic integration.

### context-quality

- frozen workspace install;
- pytest;
- Ruff;
- Pyright.

### context-postgres

- repository PostgreSQL infrastructure;
- migrate to current head;
- Alembic metadata check;
- deterministic seed;
- insert a versioned ProjectSummary;
- install a real NODE-33 TaskGraph;
- build L0-L3 context through the real Postgres adapter;
- verify provenance, project-data boundary and token budget;
- cleanup/reset infrastructure.

## 24. Release-blocking invariants

1. Raw chat history is not the long-project memory store.
2. Every selected context fact has source ID/version/hash.
3. L0-L4 layer order is deterministic.
4. Final rendered context fits the hard budget.
5. Required layer/source failure is explicit, never silent.
6. Cross-project retrieval is rejected before ranking.
7. Project facts do not gain system instruction authority.
8. Retrieved/user content is rendered as untrusted data.
9. Context Engine does not invoke provider SDKs or tools directly.
10. Query embeddings come through NODE-22 or an injected semantic-search port.
11. Cache is derived/replaceable and version keyed.
12. User correction is promoted as structured facts through Project-owned writes.
13. Task context is reconstructed from NODE-33 durable state.
14. No NODE-34 COMPLETE claim is allowed until required execution gates run green.
