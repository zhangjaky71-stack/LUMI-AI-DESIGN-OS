# LUMI Agent Team V1

> NODE-37 — Agent Team  
> Runtime contract: `AgentTeam:v1`  
> Depends on: NODE-28 Agent Registry, NODE-29 Deep Agents Runtime, NODE-31 Skill Runtime, NODE-33 TaskGraph, NODE-34 Context Engine, NODE-35 Memory Engine, NODE-36 Knowledge Engine  
> Status: implementation contract; completion still requires executed CI gates

## 1. Purpose

NODE-37 defines the production design team that runs on the existing LUMI Agent platform.

It does **not** create a second Agent framework.

The source of truth remains:

```text
agents/<agent-id>/<version>/agent.yaml
agents/<agent-id>/<version>/system.md
```

and every team member is loaded by the existing NODE-28 `AgentDefinitionLoader`.

Team-specific collaboration metadata lives under:

```text
AgentDefinition.metadata.team
```

so the existing Agent Definition hash/version contract remains authoritative.

## 2. Canonical 16 roles

### P0

```text
creative-director
brand-strategist
research-agent
prompt-engineer
image-generator
image-editor
workflow-engineer
critic-agent
```

### P1

```text
logo-designer
web-designer
ui-designer
video-generator
video-editor
social-media-designer
presentation-designer
data-visualization-agent
```

NODE-37 pins all 16 at:

```text
2.0.0
```

through:

```text
config/agent-team/team.v1.json
```

## 3. Candidate release policy

NODE-37 deliberately does not overwrite existing NODE-28 PRODUCTION releases.

The new 2.0.0 team versions are pinned by the immutable team manifest as candidates for NODE-37 acceptance.

Promotion to a production/default Agent Registry channel remains a separate release decision after gates are green.

## 4. Archetypes

Canonical team archetypes:

```text
dialog
deep
generator-worker
critic
```

The archetype is a runtime hint and governance classification, not a new Agent type system.

## 5. Agent Team profile

Each Agent's `metadata.team` contains:

```text
archetype
objective
can_delegate
delegation_allowlist
max_delegation_depth
delegation_tool_ceiling
delegation_permission_ceiling
timeout_profile
risk_profile
approval_gated_actions
supports_waiting_external
```

The profile is validated by `team_profile()`.

Unknown team fields fail closed.

## 6. Direct tools vs delegation ceiling

A central NODE-37 design choice is to keep these separate:

```text
direct Agent tools
!=
delegation authorization ceiling
```

Example: Creative Director directly receives only read/coordination tools:

```text
project.query
artifact.query
asset.read
```

but may be authorized by its invocation context to delegate to a child that legitimately has:

```text
web.search
asset.write-derived
sandbox.execute
media.inspect
```

This does **not** give those tools directly to Creative Director.

It only defines the maximum scope that can be narrowed into a child grant.

## 7. Delegation anti-escalation

A child delegation is accepted only when all are true:

1. parent profile allows delegation;
2. child is in parent allowlist;
3. depth is below the parent maximum;
4. runtime is not cancelled;
5. child tools are a subset of:
   `parent delegation_tool_ceiling ∩ runtime allowed_tools`;
6. child permissions are a subset of:
   `parent delegation_permission_ceiling ∩ runtime granted_permissions`;
7. a child that can itself delegate has ceilings no broader than the parent's effective ceiling.

Failure codes include:

```text
AGENT_TEAM_CHILD_NOT_ALLOWLISTED
AGENT_TEAM_DELEGATION_DEPTH_EXCEEDED
AGENT_TEAM_CHILD_TOOL_ESCALATION
AGENT_TEAM_CHILD_PERMISSION_ESCALATION
AGENT_TEAM_DELEGATION_CANCELLED
```

## 8. Bounded delegation depth

NODE-37's canonical team has exactly one top-level delegator:

```text
creative-director
```

Its maximum depth is:

```text
1
```

Every specialist is a non-delegator in V1.

This prevents specialist-to-specialist ping-pong and keeps the authorization tree inspectable.

## 9. Logical specialist chain vs authorization parent

The logical image flow is:

```text
Creative Director
  -> Brand Strategist
  -> Research Agent
  -> Prompt Engineer
  -> Image Generator
  -> Critic Agent
  -> Image Editor
```

However every structured delegation grant is issued by Creative Director.

A specialist's structured result is passed to the next specialist as prior data through Creative Director's bounded orchestration.

Specialists do not recursively re-delegate to each other.

## 10. Structured handoff input

`TeamTaskInput` contains:

```text
objective
inputs
constraints
expected_output
deadline_at?
budget_remaining_usd?
parent_task_id?
trace_id?
```

It deliberately contains no chain-of-thought field.

A child receives only the task data and prior structured results required for its stage.

## 11. Budget, deadline and cancellation propagation

`DelegationRuntimeContext` carries:

```text
allowed_tools
granted_permissions
depth
budget_remaining_usd
deadline_at
cancelled
```

`build_handoff()` requires the task budget/deadline to match the runtime delegation context.

A mismatch fails closed instead of silently changing constraints.

Cancellation is checked before the child is invoked.

## 12. Structured task result

All 16 NODE-37 definitions use:

```text
TeamTaskResult
```

Strict JSON Schema:

```text
schemas/agent-outputs/team-task-result.schema.json
```

Fields:

```text
status
summary
artifacts[]
citations[]
confidence
warnings[]
followups[]
waiting_reason?
structured_output
```

Unknown top-level fields are rejected.

## 13. Status model

Canonical statuses:

```text
SUCCEEDED
FAILED_RETRYABLE
FAILED_FINAL
WAITING_EXTERNAL
WAITING_APPROVAL
CANCELLED
```

Waiting statuses require a non-empty `waiting_reason`.

## 14. Artifact references

A specialist never returns hidden raw generated state as the durable output contract.

Artifact result identity is:

```text
artifact_id
version
kind
```

A generator/editor must not claim a produced artifact until a durable ref exists.

## 15. Citation references

Research/brand/presentation/data work can return:

```text
source_type
source_id
version
locator
```

This is intentionally aligned with NODE-36 source/citation semantics.

## 16. Role-specific safety rules

### Creative Director

- decomposes objective;
- preserves constraints;
- delegates only allowlisted specialists;
- synthesizes the final direction;
- no unbounded delegation.

### Brand Strategist

Brand hard-rule writes are not silent mutations.

Profile requires:

```text
approval_gated_actions = ["brand-rule.write"]
```

A role may return `WAITING_APPROVAL` for such a proposal.

### Research Agent

External facts must be source-backed and freshness-aware.

### Critic Agent

Critic is source-level read-only:

```text
asset.read
artifact.query
media.inspect
```

It has no `asset.write-derived`, no `sandbox.execute`, and no write permission.

A Critic result containing written artifact refs is rejected by the team result validator.

### Video Generator / Editor

Long-running provider work can return:

```text
WAITING_EXTERNAL
```

with a stable provider request reference in `waiting_reason`.

They must never fake completed video/edit artifacts while a provider job is pending.

## 17. Real Tool Gateway names

NODE-37 definitions only use P0 Tool Gateway names already present in NODE-25:

```text
web.search
web.fetch
asset.read
asset.write-derived
project.query
artifact.query
sandbox.execute
media.inspect
```

No NODE-37 definition invents an undeclared native tool.

## 18. Real Model Registry routes

NODE-37 uses NODE-23 routes already present in the Model Registry, including:

```text
reasoning.director
reasoning.default
image.general
image.hero
image.local_edit
video.general
video.edit
```

The Agent Team does not hard-code provider names or provider API keys.

## 19. Skills

Agent skills are existing NODE-31 packages resolved through the NODE-28 dependency resolver, including:

```text
creative-direction
web-research
brand-reasoning
asset-management
reference-analysis
typography-composition
image-workflow
photo-image-editing
visual-critique
webpage-building
pdf-docs
spreadsheet
```

NODE-37 adds no competing skill format.

## 20. Context, Memory and Knowledge

Team definitions reference existing context policies.

Memory access is read-oriented in NODE-37; no team definition declares direct Memory write.

Knowledge and retrieved sources remain evidence, governed by NODE-34/36 trust boundaries.

A child's prior result is structured data, not hidden parent reasoning.

## 21. Team manifest

Manifest:

```text
config/agent-team/team.v1.json
```

Schema:

```text
lumi.agent-team.v1
```

It pins:

- exact 16 member ids;
- exact 2.0.0 versions;
- P0/P1 tier;
- root Agent;
- canonical image flow.

The manifest has a deterministic content hash.

## 22. Team compiler

`compile_agent_team()`:

1. loads team manifest;
2. uses NODE-28 `AgentDefinitionLoader` for every member;
3. parses `metadata.team`;
4. validates direct tool/permission ceiling;
5. validates static delegation graph;
6. validates role invariants;
7. returns immutable definition/profile mappings.

NODE-37 contains no second `AgentDefinition` class.

## 23. Role eval contracts

File:

```text
evals/profiles/agents/agent-team-v1.json
```

Every one of 16 roles has explicit:

```text
must[]
forbid[]
```

Each Agent Definition binds a unique eval profile:

```text
team-<agent-id>-v1
```

Static role checks enforce safety/configuration markers only. They are not presented as a substitute for semantic model-quality evaluation.

## 24. Image TaskGraph plan

NODE-37 exposes:

```text
image_team_task_graph()
```

The V1 plan contains six specialist TaskGraph steps:

```text
brand
research
prompt
generate
critic
edit
```

Dependencies:

```text
brand
  -> research
brand + research
  -> prompt
prompt
  -> generate
generate
  -> critic
generate + critic
  -> edit
```

Each step owner uses the NODE-33 owner convention:

```text
AGENT:<agent-id>@2.0.0
```

Task type:

```text
AGENT_TEAM_HANDOFF
```

## 25. DAG safety

The TaskGraph plan validator rejects:

- duplicate step ids;
- self-dependencies;
- unknown dependencies;
- cycles;
- concurrent writes to the same named artifact slot when no dependency ordering exists.

The canonical image plan therefore has no unbounded loop and no uncontrolled write race.

## 26. Structured image flow execution

`execute_image_team_flow()` executes the same six specialist stages through bounded Creative Director handoffs.

Every child sees:

```text
original inputs
prior structured TeamTaskResult payloads
constraints
budget/deadline/trace
```

The flow stops immediately on:

```text
FAILED_FINAL
FAILED_RETRYABLE
CANCELLED
WAITING_EXTERNAL
WAITING_APPROVAL
```

It does not continue downstream work after a terminal/wait state.

## 27. MockProvider E2E

Script:

```text
scripts/integration_agent_team.py
```

The integration:

1. compiles all 16 definitions;
2. instantiates/exercises the real NODE-22 `MockProvider` for the Creative Director model boundary;
3. materializes the six-step TaskGraph adapter plan;
4. executes the six-specialist structured image flow;
5. executes the same input a second time;
6. requires deterministic identical results;
7. requires Critic to return no written artifact;
8. requires final image editor artifact version 2.

This is deterministic acceptance evidence, not a paid-provider benchmark.

## 28. Why MockProvider is reflection-adapted in the integration

The integration intentionally consumes the installed NODE-22 `MockProvider` through its current public callable contract rather than copying a second mock class into NODE-37.

A current package shape that cannot be constructed or invoked causes the E2E to fail; it does not silently skip the provider probe.

## 29. Production registry safety

Existing `agents/registry.json` production releases are not automatically replaced by NODE-37.

This node validates the 16 candidate team definitions through the team manifest first.

Production promotion should happen only after acceptance gates and release approval.

## 30. Release-blocking invariants

1. Exactly 16 canonical team definitions compile through NODE-28.
2. NODE-37 defines no competing `AgentDefinition`.
3. Every role has explicit team profile, output schema and eval profile.
4. All tools, skills, context, budget and model routes resolve to existing source-of-truth names.
5. Only Creative Director delegates in V1.
6. Delegation depth is one.
7. Child tools and permissions can only narrow runtime authorization.
8. Cancellation/budget/deadline propagate into handoff.
9. Structured handoff contains no hidden-reasoning field.
10. Critic has no write-capable direct tool/permission.
11. Brand hard-rule write is approval-gated.
12. Video workers support explicit external wait state.
13. Image flow contains at least four specialist Agents and is acyclic.
14. Concurrent writes to the same artifact slot require dependency ordering.
15. Creative Director MockProvider E2E is deterministic.
16. NODE-37 is not COMPLETE until required execution gates actually run green.
