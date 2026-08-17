# LUMI Context Engine V1

> NODE-34 — Runtime Context Engine  
> Current chain: NODE-28 → NODE-29 → NODE-30 → NODE-31 → NODE-32 → NODE-33 → NODE-34  
> Parent: `feat/node-33-task-graph-scheduler` @ `c3fa9cc35309b1e698274e87b98d7ed6c57d5b2a`

## 1. Purpose

NODE-34 builds a bounded, source-traceable runtime context view for one Agent task.

It is deliberately **not** a second Context Compiler and **not** a new source-of-truth store.

NODE-32 owns immutable Context Bundle compilation:

```text
source snapshots
  → precedence/conflict resolution
  → frozen constraints + frozen task facts
  → context-bundle://... + content hash
```

NODE-34 consumes that exact bundle and derives:

```text
frozen NODE-32 task context
  + authorized runtime retrieval
  + ranking
  + token budgeting
  + deterministic compression
  + safety boundaries
  → runtime-context://... + freeze hash
```

The NODE-32 bundle is never mutated, rewritten, or silently re-hashed by NODE-34.

## 2. Architectural boundary

The production path is:

```text
NODE-33 claimed AGENTIC task
        │
        ▼
ScheduledAgentTaskRequestResolver
        │ exact agent@version + context-bundle://...
        ▼
NODE-30 Agent Registry
NODE-31 Skill Registry
NODE-32 ContextBundleProvider
        │
        ├── exact Agent config
        ├── exact Skills
        └── exact PinnedContextBundle
        ▼
NODE-34 ContextRequestFactory
        │
        ├── counts NODE-29 trusted system prompt
        ├── reserves response tokens
        └── allocates dynamic context budget
        ▼
NODE-34 ContextEngine
        │
        ├── frozen task context
        ├── authorized retrieval
        ├── tenant/ACL/memory-scope filter
        ├── hybrid ranking
        ├── compression
        └── safety rendering
        ▼
runtime-context://...
        │
        ▼
ContextAwareDeepAgentTaskExecutor
        │
        ▼
NODE-29 bounded Deep Agent runtime
        │
        ▼
NODE-33 context_refs provenance handoff
```

## 3. Five semantic layers

The shared semantic model retains five layers:

| Layer | Meaning | NODE-34 V1 behavior |
|---|---|---|
| `L0_SYSTEM` | platform/runtime policy | already rendered by NODE-29; retrieval cannot write here |
| `L1_PROJECT` | stable project/brand data | dynamic project-data view |
| `L2_AGENT` | exact Agent/Skill instructions | already rendered by NODE-29; retrieval cannot write here |
| `L3_TASK` | current task + frozen task facts | required frozen NODE-32 task context |
| `L4_RETRIEVED` | Memory/Knowledge/Asset/etc. evidence | authorized runtime retrieval |

NODE-34 V1 injects only dynamic `L1/L3/L4` data into the user-side runtime context.
This prevents duplicated Agent instructions and duplicated pinned constraints.

## 4. Exact identity

A `ContextRequest` binds:

- `organization_id`
- `project_id`
- `agent_run_id`
- `task_id`
- exact `agent_ref`
- exact `context_bundle_ref`
- task objective
- purpose/query
- model input budget
- response reserve
- static prompt token reserve
- per-layer budgets
- effective memory-read scopes
- required source refs
- retrieval limit
- request metadata

Moving Agent aliases or changing a Context Bundle cannot silently change an existing
runtime view.

The manifest provenance also binds:

```text
agent:<agent@version>#<agent-content-hash>
skill:<skill@version>#<skill-content-hash>
context-bundle:<ref>@<version>#<bundle-content-hash>
```

## 5. Runtime context identity

`ContextManifest.freeze_hash` covers:

- tenant/run/task identity
- exact Agent identity
- base Context Bundle ref/hash
- request semantic hash
- selected item identities
- trust and instruction authority
- priority/token estimates
- selected content hashes
- item metadata
- source-version vector
- cache key
- final rendered-context hash
- warnings

The stable reference is:

```text
runtime-context://<organization>/<project>/<task-or-run>/<freeze_hash>
```

This reference is separate from `context-bundle://...`.

## 6. Trust and instruction authority

Trust and instruction authority are explicit, not inferred from arbitrary text.

| Trust | Authority |
|---|---|
| `TRUSTED_SYSTEM` | `system` |
| `TRUSTED_AGENT` | `agent` |
| `USER_INPUT` | `user` |
| `TRUSTED_PROJECT_DATA` | `none` |
| `UNTRUSTED_RETRIEVED` | `none` |

A mismatched trust/authority pair is invalid at contract construction.

Most importantly, retrieved candidates must already have
`instruction_authority=none`. A retrieval source attempting to supply Agent or System
authority fails closed with `CONTEXT_RETRIEVAL_AUTHORITY_ESCALATION`.

Retrieval is also forbidden from injecting data into `L0_SYSTEM` or `L2_AGENT`.

## 7. Prompt-injection boundary

Project/retrieved data is rendered inside explicit non-instruction wrappers:

```text
[TRUSTED_PROJECT_DATA ... authority=none]
...
[/TRUSTED_PROJECT_DATA]
```

or:

```text
[UNTRUSTED_RETRIEVED_DATA ... authority=none]
...
[/UNTRUSTED_RETRIEVED_DATA]
```

The inspector flags common instruction-injection shapes and secret-shaped text.
Detection creates warnings and metadata; it never promotes the content.

Suspicious data remains data.

## 8. NODE-32 frozen task context

`bundle.task_context` enters NODE-34 as one required `L3_TASK` item.

It is:

- content-hashed independently for the runtime item;
- tagged with the original Context Bundle hash and source refs;
- trusted project data, not higher-priority instruction;
- compressible under runtime token pressure;
- never written back to the immutable bundle.

Compression therefore changes only the derived runtime view.

## 9. Retrieval source contract

`ContextRetrievalSource.search(request)` is the only NODE-34 retrieval seam.

V1 includes:

- `NullContextRetrievalSource`
- `StaticContextRetrievalSource`
- `CompositeContextRetrievalSource`

Production Memory, Knowledge, Asset, Artifact and Research adapters belong behind this
port. NODE-34 itself imports no database SDK, provider SDK, HTTP client, shell, or
container runtime.

## 10. Tenant, ACL and memory scope

Filtering occurs before ranking.

A candidate is eligible only when:

1. organization matches;
2. project matches;
3. ACL is granted;
4. required Memory scope is allowed;
5. Memory items declare a required memory scope;
6. instruction authority is `none`;
7. the candidate is not trying to enter a static instruction layer.

A high semantic score never overrides these authorization rules.

## 11. Hybrid ranking

The deterministic V1 score is:

```text
0.38 * semantic
+ 0.32 * lexical
+ 0.18 * authority/source quality
+ 0.12 * recency
```

All inputs are bounded to `[0, 1]`.

Tie-breaking then uses priority, recency, version and stable item identity.
Duplicate source/version/hash identities are removed.

## 12. Token budget model

NODE-34 does not assume the whole model context window is available.

```text
dynamic_budget =
    max_input_tokens
    - response_reserve_tokens
    - static_prompt_tokens
```

`DefaultDeepAgentContextRequestFactory` computes `static_prompt_tokens` from the
actual NODE-29 trusted system prompt plus a safety margin.

The default balanced profile allocates the dynamic budget as:

```text
L1_PROJECT    25%
L3_TASK       35%   required
L4_RETRIEVED  40%
```

Production composition may supply another profile and an exact model tokenizer.

## 13. Conservative tokenizer

V1 ships a dependency-free fallback:

```text
ceil(len(utf8_bytes) / 3)
```

It is intentionally conservative and injectable.

The exact tokenizer for a selected NODE-22 model profile remains a composition gap,
not something NODE-34 guesses internally.

## 14. Compression

Compression is deterministic and provider-free.

The policy:

1. preserve bounded leading sentences that fit;
2. if none fit, binary-search a bounded character prefix;
3. add `…[compressed]` only if the suffix itself still fits;
4. preserve an `original_content_hash`;
5. never compress `compressible=False` content.

Required content that cannot fit fails closed.

## 15. Final rendered-budget enforcement

Per-layer estimates are not enough because safety wrappers also consume tokens.

NODE-34 therefore counts the **final rendered context**.

If it exceeds the dynamic budget:

1. lowest-value optional, non-pinned items are removed;
2. required compressible items may be compressed further;
3. if the view still cannot fit, build fails with
   `CONTEXT_FINAL_RENDER_BUDGET_EXCEEDED`.

The manifest can never report a token count above its hard maximum.

## 16. Required evidence

Two fail-closed controls exist:

- `ContextItem.required`
- `ContextRequest.required_source_refs`

A required item or source may not disappear silently because of ranking or budget.

## 17. Cache

The in-memory cache is a derived-view optimization only.

Cache identity includes:

- request semantic hash;
- exact source/dependency version vector;
- retrieval fingerprint including selected source, priority, relevance and freshness.

This prevents stale cache reuse when source bytes stay the same but retrieval scoring
changes.

The cache supports project and source-version invalidation.

## 18. Runtime manifest storage

`RuntimeContextManifestStore` is a persistence port.

The V1 in-memory implementation is deterministic and content-addressed.
Conflicting content at the same `runtime-context://...` identity is rejected.

Production durable storage is intentionally left to the runtime persistence/control
plane gap.

## 19. Deep Agent integration

`ContextAwareDeepAgentTaskExecutor` composes current NODE-29 ports without modifying
NODE-29's existing executor.

It:

1. resolves the scheduled task request;
2. validates run/org/project/task identity;
3. resolves exact Agent;
4. materializes exact Skills;
5. loads exact NODE-32 Context Bundle;
6. creates the NODE-34 Context Request;
7. builds and stores the runtime manifest;
8. compiles the existing NODE-29 bounded Agent runtime;
9. invokes it with objective + runtime context;
10. parses/stores the structured result;
11. appends `runtime-context://...` to NODE-33 `context_refs`.

The raw `bundle.task_context` is not appended a second time.

## 20. Ambient-authority boundary

`tools/node34/validate_context_engine.py` rejects direct NODE-34 imports of:

- provider SDKs;
- database SDKs;
- broad HTTP clients;
- Docker;
- `subprocess`.

It also rejects `os.system`, missing expected modules and package files over the
maintainability limit.

The Context Engine remains a policy/composition layer, not an ambient authority
holder.

## 21. V1 non-goals

NODE-34 does not claim:

- production PostgreSQL manifest persistence;
- production Memory retrieval;
- production Knowledge retrieval;
- production Asset/Artifact retrieval;
- exact provider tokenizer composition;
- embedding provider ownership;
- model-provider credentials;
- a second Constraint Engine;
- a second Agent Registry;
- a second Task Graph.

These are explicit gaps or owned by adjacent nodes.

## 22. Acceptance

The formal NODE-34 compatibility suite covers 15 cases:

1. exact Agent selector;
2. cross-tenant filtering before ranking;
3. Memory read-scope enforcement;
4. injection stays zero-authority with real rendered newlines;
5. deterministic manifest/cache replay;
6. retrieval-score-sensitive cache identity;
7. Context Bundle identity fail-closed;
8. frozen task-context compression without bundle mutation;
9. required uncompressible item fail-closed;
10. optional low-value budget dropping;
11. content-addressed manifest storage;
12. project cache invalidation;
13. exact Agent/Skill/Bundle provenance binding;
14. retrieval authority escalation rejection;
15. Context-aware executor runtime-ref handoff.

## 23. CI

Dedicated workflow:

```text
.github/workflows/node-34-context-engine.yml
```

Required stages:

- compile;
- static Context Engine contract validation;
- Ruff;
- 15-case pytest;
- gap-ledger JSON parse.

A GitHub Actions result with `runner_id=0` and `steps=[]` is an external runner
allocation failure, not evidence that any code/test stage ran.

## 24. Open gaps

See `reports/nodes/NODE-34/gap-ledger.json`.

The main gaps are:

- durable RuntimeContextManifest persistence;
- production retrieval backend composition;
- exact NODE-22 tokenizer composition;
- hosted runner allocation.

## 25. Next node

`NODE-35 — Memory Engine`

NODE-35 will implement governed durable Memory and expose it through the NODE-34
retrieval contract, preserving the same tenant/scope/authority boundaries.
