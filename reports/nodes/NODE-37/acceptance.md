# NODE-37 — Agent Team Acceptance

> Development branch: `node-37-agent-team`  
> Intended stacked base: `node-36-knowledge-engine-release`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Completion rule: contract, quality and E2E gates must actually execute green.

## 1. Canonical scope

Specification:

```text
docs/nodes/NODE-37-AGENT-TEAM.md
```

NODE-37 implements the 16-role LUMI design team on the existing Agent Runtime.

It does not introduce another Agent Definition format or scheduler.

## 2. Existing source-of-truth reused

All team members remain NODE-28 definitions:

```text
agents/<agent-id>/2.0.0/agent.yaml
agents/<agent-id>/2.0.0/system.md
```

Loaded by:

```text
AgentDefinitionLoader
```

Team metadata is stored in existing `AgentDefinition.metadata.team`.

## 3. Canonical P0 roles

Implemented 2.0.0 definitions:

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

## 4. Canonical P1 roles

Implemented 2.0.0 definitions:

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

Exactly 16 roles are pinned in:

```text
config/agent-team/team.v1.json
```

## 5. Candidate release policy

Existing NODE-28 production Agent releases are not silently replaced.

NODE-37 pins candidate 2.0.0 versions through its own immutable team manifest pending acceptance and release promotion.

## 6. Team profile contract

Implemented fields:

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

Unknown fields fail closed.

## 7. Archetypes

Implemented:

```text
dialog
deep
generator-worker
critic
```

## 8. Delegation model

Only:

```text
creative-director
```

can delegate in V1.

All other 15 roles are non-delegators.

Creative Director allowlist is exactly those 15 roles.

Maximum delegation depth:

```text
1
```

This removes specialist-to-specialist recursive ping-pong.

## 9. Delegation anti-escalation

`authorize_delegation()` verifies:

- parent is a delegator;
- child is allowlisted;
- runtime is not cancelled;
- depth is within limit;
- child direct tools are subset of parent effective delegation tool ceiling;
- child direct permissions are subset of parent effective permission ceiling;
- nested delegation ceilings cannot widen parent authority.

Runtime authority is:

```text
parent declared ceiling
INTERSECT
runtime allowed/granted ceiling
```

Children only narrow it.

## 10. Structured task input

Implemented `TeamTaskInput`:

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

No chain-of-thought/hidden-reasoning field exists.

## 11. Constraint propagation

Handoff requires runtime and task values to agree for:

```text
budget_remaining_usd
deadline_at
```

Cancellation stops before a child call.

## 12. Structured task result

All 16 definitions use:

```text
TeamTaskResult
```

Strict schema:

```text
schemas/agent-outputs/team-task-result.schema.json
```

Result includes:

```text
status
summary
artifacts
citations
confidence
warnings
followups
waiting_reason?
structured_output
```

Unknown result fields are rejected.

## 13. Status contract

Implemented:

```text
SUCCEEDED
FAILED_RETRYABLE
FAILED_FINAL
WAITING_EXTERNAL
WAITING_APPROVAL
CANCELLED
```

Waiting states require `waiting_reason`.

## 14. Critic safety

`critic-agent@2.0.0` direct tools:

```text
asset.read
artifact.query
media.inspect
```

It has neither:

```text
asset.write-derived
sandbox.execute
```

and no write permission.

Team result validation also rejects a Critic result that claims a newly written artifact.

## 15. Brand approval boundary

`brand-strategist` declares:

```text
approval_gated_actions = ["brand-rule.write"]
```

Brand-rule mutation is therefore a governed approval path, not silent Agent authority.

## 16. Video wait boundary

Both:

```text
video-generator
video-editor
```

use an external timeout profile and declare:

```text
supports_waiting_external = true
```

A normal non-video role returning `WAITING_EXTERNAL` is rejected.

## 17. Tool contract

Definitions only use real NODE-25 P0 names:

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

## 18. Model route contract

Definitions only use real NODE-23 route profiles:

```text
reasoning.director
reasoning.default
image.general
image.hero
image.local_edit
video.general
video.edit
```

## 19. Skill contract

The NODE-28 bootstrap dependency catalog was extended to existing NODE-31 Skill packages needed by the 16 roles.

No new Skill definition format is introduced.

## 20. Role eval contracts

File:

```text
evals/profiles/agents/agent-team-v1.json
```

All 16 roles have explicit `must` and `forbid` criteria.

Each Agent definition binds:

```text
team-<agent-id>-v1
```

Static contract checks are not represented as semantic model-quality scores.

## 21. Team manifest

File:

```text
config/agent-team/team.v1.json
```

Contains:

- schema `lumi.agent-team.v1`;
- team/version identity;
- root Creative Director;
- exact 16 member pins;
- P0/P1 tiers;
- canonical image flow.

Compiler returns immutable mappings.

## 22. Structured handoff

Implemented:

```text
TeamHandoff
build_handoff
parse_team_task_result
validate_result_for_agent
```

A child receives only original inputs, constraints and prior structured results needed for the stage.

## 23. Bounded image flow

Implemented flow:

```text
Creative Director
-> Brand Strategist
-> Research Agent
-> Prompt Engineer
-> Image Generator
-> Critic Agent
-> Image Editor
```

Authorization parent remains Creative Director for each specialist call.

This yields six specialist executions while delegation depth stays one.

## 24. Flow stop conditions

Downstream execution stops on:

```text
FAILED_RETRYABLE
FAILED_FINAL
WAITING_EXTERNAL
WAITING_APPROVAL
CANCELLED
```

No downstream Agent continues after a wait/terminal result.

## 25. TaskGraph plan

Implemented:

```text
image_team_task_graph()
```

Six steps:

```text
brand
research
prompt
generate
critic
edit
```

Each emits NODE-33 owner identity:

```text
AGENT:<agent-id>@2.0.0
```

Task type:

```text
AGENT_TEAM_HANDOFF
```

## 26. TaskGraph safety

Plan rejects:

- duplicate ids;
- unknown dependencies;
- self dependencies;
- cycles;
- unordered concurrent writes to one artifact slot.

Canonical dependencies ensure Critic reads the generated image and Editor waits for both generation and critique.

## 27. MockProvider deterministic E2E

Script:

```text
scripts/integration_agent_team.py
```

It:

1. compiles exactly 16 definitions;
2. exercises actual NODE-22 `MockProvider` against Creative Director's model boundary;
3. materializes the six-step TaskGraph adapter template;
4. requires >=4 distinct specialist owners;
5. executes the structured six-specialist image flow;
6. executes the same flow twice;
7. requires identical results;
8. verifies Critic returns no artifact;
9. verifies final edited image artifact version 2.

## 28. Unit tests

Files:

```text
apps/agent-runtime/tests/test_agent_team.py
apps/agent-runtime/tests/test_agent_team_flow.py
apps/agent-runtime/tests/test_agent_team_task_graph.py
```

Coverage includes:

- exact canonical 16 definitions;
- P0/P1 split;
- output/eval/team metadata;
- role static eval binding;
- Critic read-only;
- Brand approval;
- Video waiting;
- tool/permission narrowing;
- cancellation;
- depth limit;
- budget/deadline handoff;
- unknown result-field rejection;
- deterministic six-specialist flow;
- TaskGraph dependencies/cycle/write-race checks.

## 29. Static validator

Script:

```text
scripts/validate_agent_team_contract.py
```

Validates:

- Agent Team package presence;
- exact 16 manifest member set;
- all definitions parse through NODE-28 loader;
- existing Model Route names;
- existing Tool names;
- existing Skill/context/budget/output/eval dependency ids;
- TeamTaskInput/Result markers;
- delegation anti-escalation;
- Critic no-write;
- Brand approval gate;
- Video external-wait support;
- strict TeamTaskResult schema;
- no competing `AgentDefinition`;
- NODE-37 does not silently promote 2.0.0 candidates into old production release registry.

## 30. Local validation status

The NODE-37 development branch has been exercised locally with the repository's current frozen dependency set through:

```text
compileall
validate_agent_team_contract.py
unittest test_agent_team*.py
integration_agent_team.py
Ruff
Pyright
```

Hosted GitHub Actions remain the release authority for final completion status.

## 31. Acceptance checklist

- [x] 16 canonical role definitions implemented.
- [x] P0/P1 tier manifest implemented.
- [x] Existing AgentDefinition/loader reused.
- [x] Team metadata contract implemented.
- [x] Direct tool vs delegation ceiling separated.
- [x] Runtime tool/permission anti-escalation implemented.
- [x] Static delegation graph validation implemented.
- [x] Max depth=1 / only Creative Director delegates.
- [x] Structured TeamTaskInput implemented.
- [x] Structured TeamTaskResult + strict schema implemented.
- [x] Budget/deadline/cancellation propagation implemented.
- [x] Critic direct no-write implemented.
- [x] Brand write approval gate implemented.
- [x] Video WAITING_EXTERNAL contract implemented.
- [x] Existing Tool names used.
- [x] Existing Model Routes used.
- [x] Existing Skills registered/resolved.
- [x] 16 role eval profiles implemented.
- [x] Six-specialist image flow implemented.
- [x] TaskGraph DAG adapter implemented.
- [x] DAG cycle/write-race checks implemented.
- [x] Actual MockProvider deterministic integration implemented.
- [x] Unit tests implemented.
- [x] Static validator implemented.
- [x] Runtime documentation implemented.
- [ ] `agent-team-contract` hosted gate executed green.
- [ ] `agent-team-quality` hosted gate executed green.
- [ ] `agent-team-e2e` hosted gate executed green.

## 32. Current classification

Until required hosted gates actually execute green:

```text
IMPLEMENTED / VALIDATING / not COMPLETE
```

If GitHub again fails before runner allocation because of the account billing/spending-limit condition:

```text
IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE
```

No hosted PASS is claimed without executed steps.
