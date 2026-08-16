# Agent Registry V1 — NODE-30

## Purpose

NODE-30 is the canonical Agent configuration registry for LUMI AI Design OS. It closes the configuration-resolution seam introduced by NODE-29 and returns only frozen `ResolvedAgentConfig` values to the Deep Agents runtime.

The registry is deliberately separate from the Skill Registry (NODE-31), Model Gateway, Tool Gateway, Context Compiler, and run-state persistence.

## Invariants

1. **Exact versions are immutable.** Republishing the same `agent_id@version` with identical canonical content is idempotent. Different content fails with `AGENT_REGISTRY_IMMUTABLE_VERSION_CONFLICT`.
2. **Runtime replay never follows a mutable alias.** Publishing a parent resolves every sub-agent selector immediately and stores exact child versions in the parent release.
3. **Aliases are control-plane pointers only.** `promote()` moves an alias to an existing exact version. `rollback_alias()` restores the previous target from durable alias history without editing releases.
4. **Exact versions win over aliases.** Promotion refuses an alias that would shadow an exact version in the same scope.
5. **Visibility is fail-closed and hierarchical.** A project may resolve project → organization → global releases. It can never resolve another project or organization.
6. **Inherited exact versions cannot be shadowed.** A narrower scope must publish a different exact version when overriding an inherited Agent. This preserves previously pinned parent replay semantics.
7. **Content hash is deterministic.** It covers the normalized manifest plus exact child release hashes; timestamps, actor ids and mutable aliases are excluded.
8. **NODE-29 remains the runtime authority for permission validation.** Publication constructs the actual `ResolvedAgentConfig` before persistence, so sub-agent tool escalation and memory permission escalation fail before a release is stored.

## Scope model

Three scopes are supported:

- `global`
- `organization:<organization_id>`
- `project:<organization_id>:<project_id>`

Resolution from a project is most-specific first. Alias lookup follows the same chain. When an alias is found, its exact target must exist in the same scope as the alias.

This avoids cross-tenant existence leaks: a missing or invisible Agent resolves as `AGENT_REGISTRY_REF_NOT_FOUND` / `AGENT_REGISTRY_EXACT_VERSION_NOT_FOUND`.

## Agent manifest

`AgentManifest` is the publication contract. It contains:

- identity: `agent_id`, `version`
- role and description
- system prompt and model profile
- canonical Tool Gateway names
- exact skill refs (`skill_id@version`)
- Context Compiler policy id
- memory read/write scopes
- sandbox execute flag
- sub-agent refs
- output schema, max steps and delegation limits

Skill contents and dependency resolution are intentionally not owned by this node. NODE-31 will validate/materialize the exact skill refs.

## Publication

`AgentRegistry.publish()` performs:

1. validate the manifest using NODE-29 permission/runtime contracts;
2. resolve each sub-agent ref in the publisher's visible scope chain;
3. replace aliases with exact `agent_id@version` refs;
4. compute a SHA-256 stable hash over normalized manifest + child hashes;
5. construct the exact NODE-29 `ResolvedAgentConfig` to catch privilege escalation;
6. write the immutable release through `AgentRegistryStore`.

Published provenance uses:

`agent-registry://<scope>/<agent_id>/<exact_version>`

## Promotion and rollback

Aliases are versioned pointer records with monotonically increasing `revision` and a target history.

Promotion never copies or mutates a release. Rollback pops one prior target and creates another alias revision. This makes rollback a control-plane action rather than a content rewrite.

## Runtime resolution

`AgentRegistry.resolve(agent_ref=..., context=...)` implements the NODE-29 `AgentConfigResolver` protocol directly.

The returned root config includes:

- exact root version;
- deterministic `content_hash`;
- immutable provenance ref;
- exact child versions;
- child provenance refs.

No mutable alias is present in the returned runtime configuration.

## Git-workspace persistence

`GitWorkspaceAgentRegistryStore` persists normalized JSON using an atomic temp-file + `fsync` + `os.replace` write.

Layout:

```text
<registry-root>/
  scopes/
    global/
      agents/<agent-id>/
        versions/<version>.json
        aliases/<alias>.json
    organizations/<org-id>/
      shared/agents/...
      projects/<project-id>/agents/...
```

The adapter intentionally does **not** invoke `git`, carry GitHub credentials, or perform network calls. The registry root is designed to be a Git-controlled configuration workspace. Commit signing, protected-branch review and remote push remain deployment/control-plane responsibilities, keeping credentials out of the agent runtime process.

## P0 acceptance

NODE-30 requires deterministic tests for:

- immutable exact versions and idempotent republish;
- alias promotion and rollback;
- project/org/global visibility and cross-tenant denial;
- publish-time sub-agent alias pinning;
- stable parent hash after alias movement;
- direct compatibility with NODE-29 `AgentConfigResolver`;
- Git-workspace JSON round-trip.

## Explicit boundary for NODE-31

NODE-30 requires syntactically exact skill refs but does not fetch, evaluate or materialize Skill content. NODE-31 owns:

- Skill manifest/dependency DAG;
- eval/policy gate;
- immutable Skill publication;
- exact-version materialization into `/skills/<id>/<version>`;
- Skill provenance and content hashes.
