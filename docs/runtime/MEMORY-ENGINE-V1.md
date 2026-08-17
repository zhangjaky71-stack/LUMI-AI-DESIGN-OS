# LUMI AI Design OS — Memory Engine V1

Status: NODE-35 implementation baseline

## 1. Responsibility

Memory Engine V1 is the durable runtime memory boundary for Agent execution. It stores
approved durable facts, preferences, decisions, episodes, summaries, and artifact notes
without turning remembered text into executable instructions.

It is intentionally separate from:

- NODE-32 Context Compiler, which freezes immutable task/context bundles;
- NODE-34 Context Engine, which retrieves and budgets runtime context;
- Agent system prompts and Skills, which own executable instruction authority.

Memory enters NODE-34 only as `L4_RETRIEVED / MEMORY / UNTRUSTED_RETRIEVED` data with
`InstructionAuthority.NONE`.

## 2. Core invariants

### 2.1 Immutable revisions

A logical memory key is an append-only revision chain. Updating a memory creates a new
revision; an existing revision is never mutated. Each revision binds:

- organization and project tenancy;
- resolved memory scope;
- logical memory key and kind;
- content hash;
- parent memory ref;
- actor/run/task provenance;
- source refs and metadata;
- confidence, importance, expiry, and idempotency identity.

The canonical ref is content-addressed:

`memory://<org>/<project-or-org>/<scope>/<key>/r<revision>/<sha256>`

### 2.2 Optimistic concurrency

Writers may supply `expected_parent_ref`. A write is accepted only when the current head
matches the expected parent. Concurrent stale writers fail closed with
`MEMORY_REVISION_CONFLICT`.

### 2.3 Idempotent writes

An idempotency key is scoped to the organization. Replaying the same semantic write
returns the existing revision. Reusing an idempotency key for different content or
identity fails closed.

### 2.4 Forget is a tombstone

V1 `forget` appends a `TOMBSTONE` revision. It removes the logical memory from normal
recall without rewriting historical provenance. Legal/administrative hard purge is a
separate governance concern and is recorded in the gap ledger.

## 3. Scope model

Supported scopes:

| Scope | Storage tenancy | Permission examples |
|---|---|---|
| project | current project | `project`, `project:<project-id>` |
| brand | current project + brand subject | `brand`, `brand:acme` |
| user | organization-wide + user subject | `user`, `user:u1` |
| organization | organization-wide | `organization`, `organization:<org-id>` |

A brand/user subject is mandatory. Project/organization identifiers are resolved from the
runtime access context when omitted.

Read/write authority is the intersection of Agent-declared memory permissions and the
invocation permission envelope. Write scopes must remain a subset of read scopes.

## 4. Tenant isolation

Project and brand memory is stored under a project boundary. Organization and user
memory is organization-wide and may be recalled from another project only inside the
same organization and only when the requested memory permission permits it.

No query path accepts a caller-supplied organization/project override after access has
been constructed. Search is always anchored to the authenticated runtime context.

## 5. Retrieval and ranking

V1 retrieval is deterministic and dependency-light. It filters before ranking:

1. organization/project visibility;
2. read permission and exact/broad memory scope;
3. active status;
4. expiry;
5. requested memory kind;
6. lexical query relevance.

Ranking combines lexical relevance, importance, confidence, and recency. The public
contract deliberately leaves semantic/vector retrieval behind the `MemoryStore` and
future retrieval-adapter boundary so V1 does not hard-code a vendor.

## 6. Context Engine integration

`MemoryContextRetrievalSource` implements NODE-34's retrieval source shape. It converts
authorized `MemoryHit` values into `RetrievalCandidate` values with these fixed security
properties:

- layer: `L4_RETRIEVED`;
- kind: `MEMORY`;
- trust: `UNTRUSTED_RETRIEVED`;
- instruction authority: `NONE`;
- `required_memory_scope` is always populated;
- content is preserved as data even when it contains prompt-injection text.

NODE-34 performs its own second tenant/scope/authority filter before ranking, giving the
integration two independent fail-closed boundaries.

## 7. Private reasoning boundary

Memory metadata rejects private-reasoning keys such as chain-of-thought, scratchpad, and
private reasoning. Memory is for durable user/project facts and decisions, not hidden
model reasoning.

## 8. Persistence

`InMemoryMemoryStore` is the deterministic test/reference implementation.

`GitWorkspaceMemoryStore` persists canonical JSON revisions with temp-file + fsync +
atomic replace. On startup it scans existing revisions, reconstructs heads and
idempotency indexes, and validates:

- root revision starts at 1 with no parent;
- revisions are contiguous;
- each parent ref matches the previous immutable revision;
- refs and idempotency entries do not conflict.

Corrupt persisted chains fail startup rather than silently repairing history.

The workspace store does not invoke Git, access the network, or own provider credentials.
Production database/vector persistence remains an adapter concern.

## 9. Runtime API

Primary operations:

- `write(request, access)` — append an immutable active revision;
- `forget(...)` — append a tombstone revision;
- `get_head(...)` — return the current active, non-expired head;
- `search(request, access)` — authorized deterministic recall.

The API does not expose mutation of historical revisions.

## 10. Acceptance coverage

NODE-35 tests cover:

1. immutable revision chains;
2. idempotent retry;
3. idempotency conflict;
4. optimistic-parent conflict;
5. write permission denial;
6. cross-project isolation;
7. cross-organization isolation;
8. same-organization organization-memory visibility;
9. tombstone forget semantics;
10. expiry filtering;
11. private-reasoning metadata rejection;
12. zero-instruction-authority Context integration;
13. exact memory-scope filtering;
14. Agent/invocation permission intersection;
15. Git workspace restart/replay roundtrip.

## 11. Non-goals for V1

NODE-35 does not claim to provide:

- production PostgreSQL/vector indexes and migrations;
- legal hard-delete/purge workflow;
- embedding generation or learned semantic reranking;
- autonomous memory extraction from hidden model reasoning;
- a policy that permits retrieved memory to become system/Agent instructions.

Those concerns remain explicit downstream integrations rather than hidden behavior.
