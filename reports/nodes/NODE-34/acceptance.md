# NODE-34 Acceptance — Context Engine V1

## Status

**IMPLEMENTED → VALIDATING**

Hosted GitHub Actions PASS is not claimed until a real runner executes the workflow.
The immediately preceding Agent-chain nodes have an account-level GitHub Actions
billing/spending-limit condition where jobs complete with `runner_id=0` and
`steps=[]`. NODE-34 keeps that external blocker visible rather than treating a
zero-step failure as a code failure.

## Parent

```text
base branch: feat/node-33-task-graph-scheduler
base commit: c3fa9cc35309b1e698274e87b98d7ed6c57d5b2a
```

## Implemented scope

- five-layer Context semantic contract;
- strict trust ↔ instruction-authority mapping;
- exact Agent and NODE-32 bundle identity checks;
- frozen NODE-32 task-context consumption without bundle mutation;
- exact Agent/Skill/Bundle hash binding;
- tenant/project filtering before ranking;
- Memory read-scope filtering;
- ACL fail-closed filtering seam;
- deterministic hybrid retrieval;
- dynamic token budgeting after NODE-29 static prompt reserve;
- deterministic compression;
- exact final-render budget enforcement;
- required source/item fail-closed handling;
- prompt-injection/secret-shape detection with zero-authority wrappers;
- source-version-aware LRU cache;
- content-addressed runtime manifest;
- RuntimeContextManifestStore protocol + deterministic in-memory adapter;
- Context-aware NODE-29 executor composition;
- runtime manifest ref handoff to NODE-33 `context_refs`;
- ambient-authority static validator;
- dedicated NODE-34 CI workflow.

## Local validation

The NODE-34 isolated compatibility harness completed:

```text
pytest tests/test_context_engine_node34.py    15/15 PASS
python compileall                            PASS
NODE-34 static contract validator            PASS
100-character source/test line check         PASS
```

The local harness uses compatibility stubs only for imported NODE-29 contracts because
the available execution container is not a repository checkout. It does not replace
hosted repository integration validation.


## Acceptance cases

| # | Invariant | Evidence |
|---|---|---|
| 1 | Agent selector must be exact | `test_request_requires_exact_agent_version` |
| 2 | tenant filter precedes ranking | `test_cross_tenant_is_filtered_before_ranking` |
| 3 | Memory requires authorized scope | `test_memory_scope_is_enforced` |
| 4 | retrieved injection has zero authority | `test_untrusted_injection_has_zero_authority_and_real_newlines` |
| 5 | manifest/cache identity deterministic | `test_manifest_is_deterministic_and_cache_replays` |
| 6 | bundle mismatch fails closed | `test_bundle_identity_mismatch_fails_closed` |
| 7 | compression never mutates NODE-32 bundle | `test_frozen_task_context_compresses_without_bundle_mutation` |
| 8 | required uncompressible data fails closed | `test_required_uncompressible_item_fails` |
| 9 | optional low-value data can drop | `test_low_priority_optional_item_drops_by_budget` |
| 10 | runtime store is content-addressed/idempotent | `test_manifest_store_is_content_addressed_and_idempotent` |
| 11 | project cache invalidation works | `test_cache_invalidation_by_project` |
| 12 | exact Agent/Skill/Bundle hashes are bound | `test_runtime_view_binds_agent_bundle_skill_versions` |
| 13 | cache identity binds retrieval scoring | `test_cache_key_changes_when_retrieval_score_changes` |
| 14 | retrieval cannot escalate instruction authority | `test_retrieval_cannot_escalate_instruction_authority` |
| 15 | runtime ref reaches TaskGraph context refs | `test_context_aware_executor_persists_runtime_ref` |

## Security boundary

`tools/node34/validate_context_engine.py` rejects ambient imports in the NODE-34
package for provider/network/database/process stacks. Source collection remains behind
injected ports.

Retrieved project/web/file/memory/knowledge data has `instruction_authority=none`.
NODE-34 never promotes retrieved text to trusted system or Agent instruction.

## No false completion

NODE-34 is not marked COMPLETE while any required hosted gate has not actually run.

If GitHub reports:

```text
runner_id = 0
runner_name = ""
steps = []
```

the hosted state is classified `BLOCKED_EXTERNAL`.

## Next

`NODE-35 — Memory Engine`
