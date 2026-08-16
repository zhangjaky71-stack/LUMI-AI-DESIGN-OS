# NODE-30 — Acceptance Evidence

Status: **IMPLEMENTED → VALIDATING → BLOCKED_EXTERNAL**

NODE-30 implements the canonical Agent Registry and directly satisfies NODE-29's `AgentConfigResolver` seam.

## Implemented

- `AgentManifest`, `AgentScope`, `PublishedAgent`, and versioned `AgentAlias` contracts.
- Immutable exact-version publication with idempotent same-content republish.
- Deterministic SHA-256 content hash over normalized manifest + exact child hashes.
- Project → organization → global visibility with no sibling/cross-tenant resolution.
- Publish-time sub-agent alias resolution and exact-version pinning.
- Alias promotion with monotonically increasing revision.
- Alias rollback using durable target history.
- `AgentRegistry.resolve()` returning NODE-29 `ResolvedAgentConfig` / `ResolvedSubagent`.
- Runtime provenance refs using `agent-registry://`.
- In-memory store for deterministic tests.
- `GitWorkspaceAgentRegistryStore` with canonical JSON layout and atomic file replacement.

## P0 boundaries

- A published exact version cannot be overwritten with different content.
- Mutable aliases never enter a resolved runtime config.
- Alias targets must exist in the same scope as the alias.
- Exact versions take precedence over aliases.
- Narrower scopes cannot shadow an inherited exact version; overrides require a new version.
- Parent releases remain replay-stable after a child alias is promoted.
- Child tool escalation is rejected by the NODE-29 runtime contract before publication.
- Project-scoped configuration cannot be resolved from another project or organization.
- Registry persistence never executes host `git` or owns GitHub credentials.

## Authored tests

`apps/agent-runtime/tests/test_agent_registry_node30.py` covers:

1. exact-version immutability and idempotency;
2. promotion + rollback history;
3. cross-tenant visibility denial;
4. sub-agent alias pinning and stable replay hash;
5. NODE-29 resolver compatibility;
6. Git-workspace release/alias round-trip.

## Persistence evidence policy

The Git-workspace adapter writes canonical Agent Registry files suitable for a protected Git configuration repository. Remote commit signing, PR approval, and push are deployment/control-plane concerns and are intentionally not performed inside `agent-runtime`.

## External validation status

GitHub hosted execution was already blocked on NODE-29 by account payment/spending-limit runner allocation (`runner_id=0`, no steps). NODE-30 therefore must not claim hosted pytest/Ruff/Pyright success until a runner actually executes the workflow.

Local/source validation may be recorded separately; it is not a substitute for hosted CI evidence.

## Next node

**NODE-31 — Skill Registry V1**

NODE-31 should consume exact `skill_id@version` refs emitted by this registry and own immutable Skill publication, dependency/eval gates, materialization paths, and Skill provenance.
