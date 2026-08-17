# LUMI Agent Team V1 — NODE-37

Status: `IMPLEMENTED / VALIDATING`

## 1. Topology

NODE-37 defines one orchestration role plus sixteen specialist roles:

```text
Director
├─ Brief Agent
├─ Research Agent
├─ Brand Strategy Agent
├─ Creative Director
├─ Moodboard Agent
├─ Copywriting Agent
├─ Typography Agent
├─ Layout Agent
├─ Image Agent
├─ Image Edit Agent
├─ Product Render Agent
├─ Video Agent
├─ Critic Agent
├─ Brand Consistency Agent
├─ Identity Agent
└─ Export Agent
```

The NODE specification says both "16 AgentDefinition" and shows Director plus 16 specialists. The
runtime topology is therefore frozen as **17 roles total = 1 Director + 16 specialized agents**.

## 2. Role boundary

Each role has an explicit immutable `TeamRoleDefinition` with:

- role identity and role kind;
- system responsibility;
- direct tool allowlist;
- exact skill refs;
- context policy;
- memory read/write scopes;
- delegation ability and allowlist;
- approval-gated actions;
- artifact production capability.

The role definition compiles into the existing NODE-30 `AgentManifest` rather than introducing a
parallel agent-registry model.

## 3. Director security model

Director is a control-plane role, not a super-agent. Its direct tool set is intentionally restricted
to:

```text
project.query
task.query
artifact.query
agent.delegate
```

It does not directly receive image generation, image editing, video generation, artifact-write, shell,
or export execution capabilities.

NODE-29/30 currently reject subagents whose tools exceed the parent direct tool set. That is useful
for ordinary nested agents, but it would force Director to hold every specialist tool. NODE-37
therefore keeps `AgentManifest.subagent_refs` empty for the Director and freezes a separate Team
Delegation Policy at the control-plane boundary.

This preserves the invariant:

```text
Director may dispatch a specialist
!=
Director may execute the specialist's tools
```

## 4. Delegation anti-escalation

Only Director may delegate in V1. Specialists cannot dynamically delegate to another specialist.

For a Director -> Specialist dispatch:

```text
effective_tools = child_direct_tools ∩ invocation_tools
```

The child never receives a tool absent from the invocation grant, and the Director never inherits the
child's direct tools. Delegation depth is one for V1.

This is stricter than recursive multi-agent autonomy and is intentional for the first production
baseline. Later delegation expansion must preserve the same capability-intersection rule.

## 5. Structured handoff

Every role returns `TeamHandoffEnvelope`:

```text
status
summary
structured_output
artifact_refs
knowledge_refs
proposed_operations
risks
open_questions
confidence
producer_agent_id?
```

Successful role outputs have machine-required structured keys. Downstream orchestration must not
parse prose to recover critical fields.

Examples:

- Brief Agent: `brief`, `assumptions`, `ambiguities`;
- Research Agent: `findings`, `citations`;
- Brand Strategy: `positioning`, `audience`, `message_pillars`, `tone`;
- Layout: `operations`;
- Critic: `critique`, `repair_plan`;
- Export: `files`.

## 6. Producer / reviewer separation

Producer and reviewer roles are explicitly separated.

Producer examples:

- Moodboard Agent;
- Copywriting Agent;
- Typography Agent;
- Layout Agent;
- Image Agent;
- Image Edit Agent;
- Product Render Agent;
- Video Agent.

Reviewer/validator examples:

- Critic Agent;
- Brand Consistency Agent;
- Identity Agent.

Critic cannot write an Artifact and cannot review an output it is identified as producing. Producer
roles cannot self-approve.

## 7. Design safety boundaries

- Layout proposes Design IR operations and must use `constraint.validate`; it cannot write renderer
  internals directly.
- Image/Image Edit/Product Render use governed model operations; they do not hold provider keys.
- Brand Strategy requires approval for persistent `brand-rule.write`.
- Research uses Knowledge/Web data but retrieved instructions remain untrusted data.
- Export Agent only creates an export plan; actual rendering/export remains a service/worker action.
- Video Agent plans long-running work and delegates execution to task/worker infrastructure.

## 8. Role eval profile

All 17 roles receive deterministic policy/effect smoke profiles.

- baseline: at least 20 cases per role;
- core Brief / Research / Layout / Image Edit / Critic: 50 cases each;
- total deterministic cases: 490.

Focus dimensions include:

```text
role boundary
structured handoff
tool minimization
prompt injection resistance
citation discipline
constraint preservation
approval gating
failure reporting
confidence calibration
provenance preservation
```

Provider-backed quality scoring remains a production integration gap; deterministic policy coverage is
not represented as a live-model quality benchmark.

## 9. Coffee poster Mock E2E

NODE-37 freezes a nine-stage mock plan:

```text
Brief
-> Research + Brand Strategy
-> Creative Direction + Moodboard
-> approval
-> Copy + Typography + Layout + Image
-> Critic + Brand Consistency + Identity
-> Image Edit + Layout repair
-> Export
-> Director complete
```

Production and review fan-outs are parallelizable. The approval stage is explicit and cannot be
silently skipped by the mock plan.

## 10. Integration gaps

`reports/nodes/NODE-37/gap-ledger.json` tracks production work intentionally left outside this node:

1. publish/evaluate the declared skill packages through SkillRegistry;
2. adapter from Team Delegation Grant to NODE-29 Deep Agent invocation;
3. live Recipe/TaskGraph approval and worker execution;
4. governed provider-backed role quality evals;
5. bind logical role tool IDs to production Tool Gateway capabilities.

## 11. Acceptance

NODE-37 contract acceptance requires:

- 17-role canonical topology;
- all roles compile to current AgentManifest;
- allowed tools and skills explicit;
- Director specialist tools absent from its direct permission set;
- delegation grant cannot exceed invocation or child role tools;
- specialists cannot recursively delegate in V1;
- structured handoff keys enforced;
- producer/reviewer separation enforced;
- 490 deterministic role-policy cases generated;
- coffee-poster mock flow validates stage order and approval;
- dedicated Python 3.12 CI executes validator, pytest, Ruff and Pyright.

Next node after acceptance: **NODE-38 — Design IR Runtime**.
