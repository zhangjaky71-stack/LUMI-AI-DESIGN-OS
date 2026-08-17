# NODE-37 Acceptance — LUMI Agent Team V1

## Status

`IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL`

The NODE-37 source contract is implemented on `feat/node-37-agent-team` and stacked on the current
`feat/node-36-knowledge-engine` line. Hosted PASS is not claimed.

## Topology clarification

The node specification contains a count ambiguity: it asks for "16 AgentDefinition V1" while its
explicit topology lists Director plus sixteen specialists. NODE-37 freezes the topology as:

```text
17 runtime roles = 1 Director + 16 specialized agents
```

No specialist role is silently dropped to satisfy the inconsistent count wording.

## Delivered

- canonical 17-role Agent Team catalog;
- every role compiles into the existing NODE-30 `AgentManifest` contract;
- explicit direct tools, exact skill refs, context policy and memory scopes per role;
- Director control-plane-only direct permissions;
- separate Team Delegation Policy so Director dispatch does not require specialist direct tools;
- effective child tools are the intersection of child role tools and invocation tools;
- V1 delegation depth fixed to one and specialist-to-specialist delegation denied;
- common machine-readable `TeamHandoffEnvelope`;
- role-specific required structured output fields;
- producer / Critic / validator separation;
- Critic artifact-write prohibition;
- Brand Strategy persistent rule write approval gate;
- Layout Agent Constraint Engine boundary;
- 490 deterministic role-policy eval cases;
- 9-stage coffee-brand poster mock E2E plan with explicit approval;
- static architecture validator;
- dedicated Python 3.12 / uv frozen-install GitHub Actions gate;
- explicit five-item production integration gap ledger.

## Deterministic eval matrix

All roles receive at least 20 policy/effect smoke cases. The five core roles required by the node are
expanded to 50 cases each:

- Brief Agent;
- Research Agent;
- Layout Agent;
- Image Edit Agent;
- Critic Agent.

Total generated deterministic cases: **490**.

These cases validate contract/security behavior. They are not represented as provider-backed visual or
creative quality scores.

## Coffee poster mock E2E

The frozen mock path is:

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

The production and review phases are explicitly separate and parallelizable.

## Validation truthfulness

The current execution container could not clone GitHub because external DNS/network access was
unavailable (`Could not resolve host: github.com`). Therefore local full-repository pytest/Ruff/Pyright
PASS is **not claimed** from this environment.

The first dedicated hosted workflow attempt for PR #104 was run `32007163132`. Its `agent-team` job
`95318913276` ended with:

```text
status=completed
conclusion=failure
steps=[]
```

No checkout, dependency install, validator, pytest, Ruff or Pyright step executed. This is classified
as `BLOCKED_EXTERNAL`, consistent with the hosted runner-allocation failure on preceding nodes. It is
not a NODE-37 code or test failure.

The dedicated hosted workflow must eventually execute the following before NODE-37 may become
COMPLETE:

1. `uv sync --all-packages --frozen`;
2. `NODE37_AGENT_TEAM_VALIDATION_PASS`;
3. `apps/agent-runtime/tests/test_agent_team_node37.py` green;
4. 17 role manifests compile;
5. 490 eval cases validate;
6. coffee-poster mock plan validates;
7. gap ledger parses with exactly 5 tracked production gaps;
8. Ruff green;
9. Pyright green;
10. preceding stacked NODE-28 through NODE-36 dependencies remain resolved in order.

## Production qualification

The following are intentionally tracked as later integration work and are not claimed complete here:

- publish/evaluate the declared skill packages through NODE-31 Skill Registry;
- translate Team Delegation Grants into NODE-29 Deep Agent invocations;
- execute the mock plan through live Recipe/TaskGraph/approval/worker infrastructure;
- run governed provider-backed role quality evals;
- bind logical role tool IDs to production NODE-25 Tool Gateway capabilities.

See `reports/nodes/NODE-37/gap-ledger.json`.

Canonical architecture: `docs/runtime/AGENT-TEAM-V1.md`

Next node after acceptance: **NODE-38 — Design IR Runtime**.
