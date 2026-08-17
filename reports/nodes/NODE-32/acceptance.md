# NODE-32 Acceptance — Context Compiler V1

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Source completion

- [x] Immutable `ContextSourceSnapshot` contract with exact source URI/version/hash.
- [x] Organization / project / brand / user / task scope isolation.
- [x] Compile-time NODE-29 memory-read authorization for persistent sources.
- [x] Exact NODE-14 seven-level source precedence.
- [x] Exact NODE-14 24-type constraint vocabulary.
- [x] NODE-14-compatible `(type, scope) -> source -> priority -> conflict -> severity -> id` resolution.
- [x] Explicit same-level constraint conflicts; no silent last-write-wins.
- [x] Explicit same-level fact conflicts; identical facts merge provenance.
- [x] SAFETY_SYSTEM cannot be shadowed by lower-priority sources.
- [x] NODE-14-compatible `lumi.constraint-set/1.0` effective snapshot.
- [x] Structured pinned/task facts with shadow evidence.
- [x] Raw source text is content-hash-bound but not automatically injected into task context.
- [x] Deterministic source ordering and source-order-independent bundle identity.
- [x] Tenant/task/brand/user/permission metadata embedded in hash-bound task context.
- [x] Source refs + source content hashes embedded in bundle provenance.
- [x] Content-addressed immutable `context-bundle://<org>/<project>/<sha256>` identity.
- [x] 128,000-character NODE-29 compatibility limits on pinned/task strings.
- [x] Direct NODE-29 `ContextBundleProvider` adapter returning `PinnedContextBundle`.
- [x] Runtime identity, provenance, content-hash and permission-revocation revalidation.
- [x] In-memory deterministic immutable store.
- [x] Canonical Git-workspace JSON store with atomic replace and no Git/network credentials.
- [x] Dedicated NODE-32 tests, design document, gap ledger and CI workflow.

## Local executable validation

The NODE-32 candidate was exercised in an isolated compatibility environment matching the NODE-29 contracts used by the compiler/provider boundary:

- Python source compilation: **PASS**;
- NODE-32 formal pytest: **11 passed**;
- gap ledger JSON parse: **PASS**;
- deterministic bundle/order/hash assertions: **PASS**;
- Git-workspace canonical roundtrip: **PASS**.

This local evidence is contract-level supporting evidence only. It is not a substitute for canonical hosted repository execution.

## Contract boundary

NODE-32 does not create a second Constraint Engine. Constraint enforcement remains NODE-14 plus its runtime validation adapters. NODE-32 only selects, freezes and proves the exact context snapshot passed to Agent runtime.

Production source collection/retrieval is not claimed. The compiler consumes already-bounded structured snapshots; later collectors/adapters must preserve the exact source/version/hash/scope contract.

Remote Git synchronization/signing/credentials are also outside this runtime module.

## Hosted validation required before COMPLETE

Do **not** mark NODE-32 COMPLETE until:

1. GitHub Actions allocates a real runner;
2. the dedicated NODE-32 workflow executes checkout/install/Ruff/pytest rather than ending before steps start;
3. NODE-32 Ruff is green under canonical Python 3.12 configuration;
4. `apps/agent-runtime/tests/test_context_compiler_node32.py` is green in hosted execution;
5. repository CI/security gates are green;
6. the stacked NODE-29 -> NODE-30 -> NODE-31 dependency chain is resolved in order.

The repository's current hosted Actions account/billing condition has already produced zero-runner, zero-step failures on the preceding Agent nodes. Such a result is **BLOCKED_EXTERNAL**, not a source-code failure and not a PASS.

## Next engineering node

**NODE-33 — Task Graph & Scheduler**.
