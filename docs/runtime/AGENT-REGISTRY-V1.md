# LUMI Agent Registry V1

> NODE: 30  
> Phase: 4 — Agent Intelligence  
> Status: IMPLEMENTED / VALIDATING  
> Depends on: NODE-23 Capability Registry, NODE-25 Tool Gateway, NODE-29 Deep Agents Runtime

## Purpose

NODE-30 makes an Agent a reproducible, versioned runtime contract instead of a mutable prompt hidden in application code. Every runnable AgentDefinition lives in Git under:

```text
agents/<agent-id>/<semver>/agent.yaml
agents/<agent-id>/<semver>/system.md
```

`agent.yaml` intentionally uses JSON syntax, a valid YAML 1.2 subset, so P0 needs no extra YAML runtime dependency.

## Immutable AgentDefinition

A definition freezes Agent id/version/role/description, model policy, Tool requirements, Skill requirements, Context policy, Memory scopes, Budget policy, permissions, output schema, eval profile, static system prompt, step limit and deterministic hashes.

The same `agent-id@version` must not be edited into different semantics. Semantic changes create a new version.

## Static prompt trust boundary

`system.md` contains trusted static instructions only. User text, web content, retrieved documents, project artifacts and memory are not interpolated into it. The linter rejects template markers such as `{{`, `{%` and `${`, NUL bytes and secret-like content. Dynamic material belongs to later Context Compiler/Memory boundaries.

## Resolution semantics

Supported selectors include exact SemVer, `1.x`, caret ranges such as `^1`, tilde ranges such as `~1.2`, and aliases such as `production`.

Rules:

- ranges choose only `PRODUCTION` releases;
- newer `CANDIDATE` versions never win a range;
- `production` must point to an exact `PRODUCTION` version;
- exact `DEPRECATED` versions remain resolvable for historical resume;
- exact `DRAFT` and `DISABLED` releases are not runnable;
- `DISABLED` is never an alias target.

Resolution freezes an exact version before execution.

## Release manifest

Mutable release state is separated from immutable version directories in `agents/registry.json`.

Statuses are `DRAFT`, `CANDIDATE`, `PRODUCTION`, `DEPRECATED`, and `DISABLED`. P0 allows one production release per Agent.

Committed examples include Creative Director 1.0.0 DEPRECATED, 1.1.0 PRODUCTION, 1.2.0 CANDIDATE, Researcher 1.0.0 PRODUCTION and Critic 1.0.0 PRODUCTION.

## Promotion and rollback

Production promotion requires two independent gates:

1. full Agent validation, including dependency and static prompt policy;
2. a passing eval release gate for the declared eval profile.

Promotion deprecates the old production release, promotes the candidate, moves the `production` alias and increments manifest revision.

Rollback may target only a previously released PRODUCTION/DEPRECATED version with passed eval evidence. It changes release metadata and alias only; it never mutates AgentDefinition files or existing AgentRun provenance.

## Dependency freeze

AgentDefinition stores policy/constraint references. Resolution freezes exact dependency evidence into AgentProvenance.

Model policy resolves through NODE-23 and records Registry version/content hash/source reference. Tools resolve through NODE-25 and record exact Tool version plus a deterministic hash of risk, runtime, permissions, input schema and output schema.

Skills use a deterministic bootstrap version catalog only until NODE-31 exists. Context, Budget, output-schema and eval-profile references also use small bootstrap catalogs in P0. These are temporary validation adapters, not competing permanent registries.

Inline Memory policy is content-hashed as dependency evidence.

## AgentRun provenance

A resolved Agent freezes requested reference, exact version, release status, definition hash, prompt hash, manifest revision and all exact dependency evidence into a deterministic `freeze_hash`.

`to_deep_agent_definition()` carries definition and provenance hashes into NODE-29 metadata before execution.

Migration `0014_agent_registry_provenance` adds append-only `agent_run_provenance`. One AgentRun can have only one frozen provenance row. Replaying an identical freeze is idempotent; a different freeze for the same AgentRun conflicts.

The store verifies organization/project scope before insert. Runtime receives SELECT/INSERT only; UPDATE and DELETE are revoked. Dependency evidence is capped at 1 MiB.

## Database validation boundary

Store semantics are covered by deterministic injected-connection tests: first freeze, replay, conflict and tenant/project mismatch. The PostgreSQL CI gate runs the real Alembic migration and verifies database schema/permissions without claiming a connector-authored live provenance write fixture. The connector rejected an integration fixture containing seeded-DB mutation/cleanup operations, so that limitation is explicit.

## NODE-29 integration

NODE-30 supplies immutable product-level Agent configuration; NODE-29 still owns bounded Deep Agents execution. The adapter carries Agent id/version, model profile, allowed tools, static prompt, step limit, definition/provenance hashes, output schema, eval profile, Skill, Context and Budget references.

## Example resolution

```text
creative-director@^1          -> 1.1.0
creative-director@production  -> 1.1.0
creative-director@1.0.0       -> 1.0.0 (DEPRECATED exact resume)
creative-director@1.2.0       -> 1.2.0 (explicit CANDIDATE exact)
```

The range does not select 1.2.0 while it is only CANDIDATE.

## Security boundary

The Agent Registry package is declarative control-plane code. Static validation rejects direct provider SDK, broad HTTP, subprocess, asyncpg and SQLAlchemy imports from the runtime package. Agent Registry does not execute tools, invoke models or gain ambient network/database authority.

## CI

Dedicated `.github/workflows/agent-registry.yml` uses three sequential gates: contract, quality and PostgreSQL migration/privilege validation. Hosted PASS is not claimed until all required jobs actually receive a runner and execute green.

## P0 limitations

Deferred intentionally: real Skill Registry (NODE-31), dedicated Context/Memory policy registries, product release UI, canary rollout, remote AgentDefinition loading, hot mutation of running Agent versions, and live connector-authored PostgreSQL provenance write acceptance.

## Definition of Done boundary

NODE-30 scope is Git-versioned immutable AgentDefinition + SemVer/exact/alias resolution + static prompt policy + NODE-23/NODE-25 dependency freeze + temporary Skill/Context/Budget/schema/eval validation + eval-gated release promotion/rollback + immutable AgentRun provenance + NODE-29 conversion + tests/docs/CI.

Status remains `IMPLEMENTED / VALIDATING / not COMPLETE` until hosted required gates are green.
