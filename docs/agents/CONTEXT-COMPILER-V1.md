# LUMI AI Design OS — Context Compiler V1

Status: **NODE-32 / IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## 1. Purpose

Context Compiler V1 turns bounded, provenance-carrying context snapshots into one immutable runtime bundle that NODE-29 Deep Agents can replay exactly.

It owns:

- context source validation and tenant/scope matching;
- compile-time memory-read authorization;
- deterministic source ordering;
- NODE-14-compatible constraint selection and freezing;
- deterministic pinned/task fact resolution;
- explicit same-level conflicts;
- source provenance and source-content hash binding;
- content-addressed immutable context bundles;
- direct NODE-29 `ContextBundleProvider` compatibility;
- runtime identity and permission revalidation before returning a bundle.

It does **not** own:

- Design IR mutation or constraint enforcement;
- OCR, QR, image, model, web, search or knowledge retrieval execution;
- external connector collection policy;
- model prompt ranking or semantic summarization;
- durable remote Git credentials, push, signing or protected-branch policy.

NODE-14 remains the enforcement contract. NODE-32 selects and freezes context for downstream use.

## 2. Frozen NODE-14 parity

Context Compiler does not create a second constraint language.

The exact V1 constraint vocabulary is inherited:

1. `LOCK_POSITION`
2. `LOCK_SIZE`
3. `LOCK_ROTATION`
4. `LOCK_TRANSFORM`
5. `LOCK_ASPECT_RATIO`
6. `LOCK_LAYER_ORDER`
7. `LOCK_PARENT`
8. `LOCK_CONTENT`
9. `LOCK_TEXT`
10. `LOCK_ASSET`
11. `LOCK_IDENTITY`
12. `LOCK_STYLE`
13. `LOCK_BRAND`
14. `PROTECT_REGION`
15. `MUST_STAY_INSIDE`
16. `MUST_NOT_OVERLAP`
17. `MIN_MARGIN`
18. `SAFE_AREA`
19. `REQUIRE_CONTRAST`
20. `REQUIRE_SCANNABILITY`
21. `REQUIRE_TEXT_READABILITY`
22. `REQUIRE_BRAND_COMPLIANCE`
23. `REQUIRE_RESOLUTION`
24. `REQUIRE_IDENTITY_SCORE`

Severity is frozen as:

`HARD > SOFT > ADVISORY`

Source precedence is frozen as:

`SAFETY_SYSTEM > USER_EXPLICIT > APPROVED_BRAND_RULE > PROJECT_RULE > RECIPE_RULE > AGENT_INFERRED > STYLE_PREFERENCE`

For active constraints, resolution mirrors NODE-14:

1. group by `(constraint.type, canonical constraint.scope)`;
2. select the highest source precedence;
3. select maximum `constraint.priority` within that source level;
4. if remaining candidates have different `parameters`, fail with an explicit same-level conflict;
5. select strongest severity;
6. if equivalent candidates remain, select the lexicographically smallest constraint UUID while retaining equivalent-winner provenance.

A lower-precedence constraint is not silently deleted. It is emitted in `shadowed` evidence with its reason and winner identity.

## 3. Source snapshots

`ContextSourceSnapshot` is the immutable compiler input.

Each snapshot contains:

- `source_ref` — stable URI;
- `source_type` — one of the seven frozen source types;
- `scope_kind` — organization/project/brand/user/task;
- `scope_id` — exact scope identity;
- `version` — exact source version;
- zero or more structured constraints;
- zero or more structured facts;
- optional raw `source_text`;
- deterministic SHA-256 `content_hash`.

The source hash binds the complete source payload, including `source_text`. The raw source text is **not** copied into the runtime task prompt by NODE-32. This keeps replay identity while reducing an unnecessary prompt-injection path. Production source collectors can derive structured facts/constraints separately and preserve the original source by provenance reference/hash.

A source hash mismatch fails closed.

## 4. Scope and authorization

The compile request binds:

- organization UUID;
- project UUID;
- optional task UUID;
- optional brand id;
- optional user id;
- current memory-read scopes;
- context bundle version.

Every source must match its target exactly:

- organization source → request organization;
- project source → request project;
- brand source → request brand;
- user source → request user;
- task source → request task.

Non-safety, non-task sources also require an applicable NODE-29 memory-read permission. Both broad scopes such as `project` and exact scopes such as `project:<id>` are supported.

`SAFETY_SYSTEM` is always eligible for compilation when its scope identity matches. Task-local explicit context does not require a persistent memory scope because it is already bound to the exact task.

The compiled bundle stores the exact persistent memory scopes it depended on. The runtime provider rechecks them, so a permission revoked after compilation cannot be bypassed by replaying an old bundle.

## 5. Facts

Facts are structured JSON-safe values with a canonical key and one channel:

- `pinned` — durable rules/preferences/reference facts for this exact bundle;
- `task` — bounded task-specific structured context.

Fact resolution uses the same seven-level source precedence.

At the same winning source level:

- identical values merge and retain all winning provenance;
- different values produce `CONTEXT_SAME_LEVEL_CONFLICT`;
- there is no last-write-wins, timestamp tie-breaker or file-order override.

Lower-precedence facts are retained as `shadowed_*_facts` evidence.

## 6. Compiled bundle

The compiler emits an immutable `CompiledContextBundle` with:

- exact organization/project/task/brand/user identity;
- required memory scopes;
- canonical `pinned_constraints` JSON;
- canonical `task_context` JSON;
- ordered source refs;
- ordered source hashes;
- SHA-256 bundle content hash;
- content-addressed `context_bundle_ref`.

Reference format:

```text
context-bundle://<organization-uuid>/<project-uuid>/<sha256>
```

Bundle identity is calculated from canonical JSON containing:

```text
version
pinned_constraints
task_context
source_refs
```

`task_context` itself embeds source refs + source hashes and tenant/task/permission metadata, so source bytes and security-sensitive metadata are transitively bound by the bundle hash.

Compilation is order-independent: the same validated sources compile to the same bundle regardless of caller input ordering.

## 7. `pinned_constraints` format

The runtime string is canonical JSON with:

- schema `lumi.context-constraints/1.0`;
- pure NODE-14-compatible `constraint_set` using `lumi.constraint-set/1.0`;
- winning constraint provenance;
- inactive constraints;
- shadowed constraints;
- the frozen source priority declaration.

The embedded effective constraints use the NODE-14 `lumi.constraint/1.0` field shape.

The Context Compiler freezes this snapshot. NODE-14/validation runtime remains responsible for actual preflight/postflight enforcement.

## 8. `task_context` format

The runtime string is canonical JSON with:

- schema `lumi.context-task/1.0`;
- organization/project/task/brand/user identity;
- required memory scopes;
- effective pinned facts;
- effective task facts;
- shadowed pinned/task facts;
- source provenance `{source_ref, content_hash}` records.

Raw unstructured source text is deliberately excluded.

Both runtime strings are capped at 128,000 characters to match the NODE-29 `PinnedContextBundle` contract.

## 9. NODE-29 adapter

`ContextBundleProviderAdapter` implements the NODE-29 port:

```python
async def load(
    *,
    context_bundle_ref: str,
    context: DeepAgentInvocationContext,
) -> PinnedContextBundle:
    ...
```

Before returning a `PinnedContextBundle`, the adapter:

1. loads the exact immutable record;
2. recomputes the content hash;
3. verifies content-addressed ref identity;
4. cross-checks record metadata against the hash-bound `task_context`;
5. cross-checks source provenance against stored refs/hashes;
6. verifies organization/project/task identity against the invocation;
7. rechecks required memory-read scopes against the current invocation permissions;
8. returns the exact NODE-29 contract.

Any mismatch fails closed.

## 10. Persistence

Two store implementations are supplied.

### In-memory store

Used for deterministic tests and adapters. Exact references are immutable; idempotent re-put is allowed.

### Git-workspace store

Canonical layout:

```text
<root>/
  organizations/<organization-id>/
    projects/<project-id>/
      context-bundles/<content-hash>.json
```

Writes use:

1. canonical JSON + newline;
2. temporary file in the target directory;
3. flush + `fsync`;
4. atomic `os.replace`.

The adapter invokes no `git` command, owns no GitHub token and performs no network request. Remote sync, signing, branch protection and deployment mounting remain control-plane/deployment responsibilities.

## 11. Security invariants

NODE-32 freezes the following invariants:

- context sources cannot cross tenant/scope identity;
- persistent context cannot exceed the caller's memory-read permissions;
- source content is hash-bound;
- raw source text is not automatically prompt material;
- same-level conflicts are explicit;
- `SAFETY_SYSTEM` cannot be displaced by user/brand/project/recipe/agent/style context;
- bundle metadata and required permissions are hash-bound and revalidated;
- old bundles cannot bypass later permission revocation;
- exact bundle refs are immutable/content-addressed;
- no hidden timestamp/file-order tie-breaker exists;
- the compiler does not mutate Design IR or bypass NODE-14 enforcement.

## 12. Validation scope

Local compatibility validation covers:

- exact 24-type and seven-source freeze;
- NODE-14 precedence/priority/severity/id parity;
- explicit constraint and fact conflict handling;
- safety precedence;
- scope and memory authorization;
- content-addressed deterministic replay;
- raw-text isolation + source-hash binding;
- runtime permission revocation and identity checks;
- record/hash/provenance tamper detection;
- canonical atomic Git-workspace roundtrip.

Hosted CI remains authoritative for canonical Python 3.12/Ruff/repository integration once GitHub can allocate a runner.

## 13. Open production gaps

NODE-32 intentionally leaves these outside the runtime compiler:

- production collectors/adapters that read project, brand, user, organization and task sources;
- remote protected-Git synchronization/signing/credentials;
- hosted validation while the repository account cannot obtain a GitHub-hosted runner.

## 14. Next node

**NODE-33 — Task Graph & Scheduler** should consume exact Agent, Skill and Context identities from NODE-29/30/31/32 and schedule deterministic bounded task execution without weakening those contracts.
