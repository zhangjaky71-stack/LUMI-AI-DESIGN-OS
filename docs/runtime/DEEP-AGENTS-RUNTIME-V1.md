# LUMI Deep Agents Runtime V1

> NODE: 29  
> Phase: Agent Runtime  
> Status: IMPLEMENTED / VALIDATING  
> Depends on: NODE-20 Idempotency, NODE-22 Model Gateway, NODE-25 Tool Gateway, NODE-28 LangGraph Control Plane, NODE-27 Cost/Budget

---

## 1. Purpose

NODE-29 introduces Deep Agents as LUMI's high-level planning/subagent runtime without allowing the library to become a second authority plane.

The node compiles an immutable `DeepAgentDefinition` into a current Deep Agents graph, then registers the bounded compiled graph into NODE-28's exact-version durable LangGraph control plane.

The intended path is:

```text
LUMI AgentRun
→ NODE-29 Deep Agent definition/factory
→ current create_deep_agent(...)
→ bounded compiled graph
→ NODE-28 durable graph registry/executor/checkpointer
```

Inside the Deep Agent:

```text
model        → NODE-22 Model Gateway compatible model adapter
external tool → NODE-25 Tool Gateway
write safety → NODE-20 idempotency/SideEffect Gateway
budget/cost  → NODE-27
files/exec   → LUMI trusted backend, not host filesystem authority
```

---

## 2. Deep Agents is not an authority boundary

Deep Agents provides planning, subagents and virtual file/backend composition.

LUMI still owns:

- tenant/project/AgentRun identity;
- exact runtime/graph/config version;
- provider/model routing;
- tool permissions;
- HITL approval;
- side-effect idempotency;
- budget/accounting;
- Sandbox and Asset boundaries;
- checkpoint durability.

Forbidden architecture:

```text
Deep Agent → provider SDK/API key
Deep Agent → arbitrary HTTP
Deep Agent → database credentials
Deep Agent → host shell
Deep Agent → Docker socket
Deep Agent → unrestricted local filesystem
Deep Agent → arbitrary tool callable bypassing Tool Gateway
```

---

## 3. Immutable DeepAgentDefinition

The definition freezes:

```text
agent_key
runtime_version
graph_key
graph_version
agent_config_version
system_prompt
model_profile
allowed_tools
subagents
delegation limits
max_steps
planning_enabled
virtual_files_enabled
metadata
content_hash
```

A runtime version is content-addressed by deterministic SHA-256.

A changed prompt, tool scope, subagent scope, model profile or delegation policy changes the definition hash.

This hash is copied into the NODE-28 GraphDefinition metadata as:

```text
deep_agent_definition_hash
```

so a durable AgentRun can be traced back to the exact Deep Agent configuration that produced its graph.

---

## 4. Root tool scope is the ceiling

The root definition contains explicit canonical LUMI tool names such as:

```text
web.search
web.fetch
artifact.query
asset.read
asset.write-derived
sandbox.execute
```

A child subagent may only receive a subset of the root tool set.

Construction fails when:

```text
child.allowed_tools - root.allowed_tools != empty
```

At run time, the authenticated invocation context may narrow the root scope again.

Effective root tools are:

```text
definition.allowed_tools ∩ invocation_context.allowed_tools
```

A ToolProvider returning any additional tool is rejected by the factory.

---

## 5. Subagent scope

Each `DeepSubagentDefinition` freezes:

```text
name
description
system_prompt
model_profile
allowed_tools
max_steps
can_delegate
```

For P0, NODE-29 supports:

```text
root → leaf subagent
```

and rejects nested child delegation.

Why:

- nested delegation increases cost fan-out;
- retry/restart accounting becomes harder;
- a recursive delegation tree can obscure tool authority;
- current product value does not require arbitrary recursive depth.

The data contract retains bounded delegation settings so a later node can add durable nested-delegation accounting without changing the public definition vocabulary.

---

## 6. Delegation limits

`DelegationLimits` contains:

```text
max_depth
max_total_subagent_calls
max_parallel_subagents
max_children_per_agent
```

P0 hard enforcement includes:

- child count at definition construction;
- root→leaf only;
- graph recursion limit;
- graph max concurrency limit;
- child external-tool subset.

The compiled graph is wrapped by `LimitedCompiledDeepAgent`.

If a caller supplies:

```text
recursion_limit=999
max_concurrency=999
```

and the immutable definition says:

```text
max_steps=20
max_parallel_subagents=2
```

execution receives at most:

```text
recursion_limit=20
max_concurrency=2
```

Callers can narrow limits but cannot widen them.

Exact durable accounting of every nested `task` delegation is deferred because P0 forbids nested subagent delegation.

---

## 7. Model boundary

`DeepAgentModelProvider` returns LangChain-compatible models for root/subagents.

NODE-29 requires every returned model to carry the trusted marker:

```text
_lumi_model_gateway_bound = True
```

This marker is set only by the trusted composition adapter representing a NODE-22-backed model.

An arbitrary provider-native model object is rejected before `create_deep_agent` executes.

The Deep Runtime package itself does not import provider SDKs or provider API-key environment names.

---

## 8. Model profiles

Definitions reference model profiles rather than provider-native deployment names.

Examples:

```text
design-v1
research-v1
critic-v1
```

The profile resolver belongs to LUMI's model-control composition and can map through NODE-23 Registry/NODE-24 health/NODE-22 routing.

A child model profile cannot grant extra tool permissions.

Model quality/cost policy and tool authority are separate concerns.

---

## 9. Tool boundary

`LumiToolGatewayProvider` converts approved canonical LUMI tool definitions into current LangChain-compatible structured tools.

The wrapper carries trusted markers:

```text
_lumi_tool_gateway_bound = True
_lumi_tool_name = <canonical name>
_lumi_tool_version = <exact version>
```

The Deep Agent factory rejects unmarked tools or an unexpected returned tool order/scope.

This means a developer cannot silently append:

```python
requests.get
subprocess.run
random_database_writer
```

to a Deep Agent's tool list and still pass NODE-29 acceptance.

---

## 10. Stable write-tool idempotency

A Deep Agent model may retry/replay a framework tool call.

Generating a fresh random idempotency key on each invocation would defeat NODE-20.

NODE-29 therefore uses LangChain's framework-injected stable tool-call identity.

The model-facing schema exposes only:

```text
payload
```

and hides the injected `tool_call_id`.

At execution:

```text
idempotency_key = deep-agent:<agent_run_id>:<tool_call_id>
```

The key is stable across framework replay of the same tool call and is not generated by the model.

`integration_deep_agent_tool_gateway.py` verifies the current LangChain injected ToolCall path.

---

## 11. NODE-25 request mapping

`Node25ToolGatewayInvoker` dynamically constructs the current NODE-25:

```text
ToolPermissionContext
ToolRequest
```

using only constructor fields supported by the installed contract.

It supplies:

- organization;
- project when supported;
- AgentRun;
- Task;
- actor Agent;
- exact tool name/version;
- arguments;
- purpose;
- permissions;
- Agent allow scope;
- parent allow scope for subagents;
- stable idempotency key;
- trace id when supported.

NODE-25 remains authoritative for:

- risk;
- HITL;
- schema validation;
- SideEffect guard;
- output offload;
- audit/redaction.

NODE-29 does not reimplement those policies.

---

## 12. Parent→child permission narrowing

A subagent invocation context includes both:

```text
parent_allowed_tools
allowed_tools
```

and construction requires:

```text
allowed_tools ⊆ parent_allowed_tools
```

The NODE-25 permission adapter forwards:

```text
agent_allow_patterns = child.allowed_tools
parent_allow_patterns = root.allowed_tools
```

so Tool Gateway independently enforces the same non-escalation rule.

This is defense in depth:

```text
NODE-29 compile-time subset
+ NODE-29 run-context subset
+ NODE-25 parent/child policy intersection
```

---

## 13. Trusted tool metadata only

Deep Agent tool descriptions come from a trusted LUMI ToolDefinition snapshot.

Remote MCP/self-described risk metadata is not used here; NODE-26 already maps MCP tools into LUMI ToolDefinition only after admin policy.

A Deep Agent therefore sees the LUMI-approved tool contract, not raw third-party server policy text.

---

## 14. Backend boundary

Deep Agents' backend parameter is supplied by `DeepAgentBackendProvider`.

Every production backend must carry:

```text
_lumi_backend_bound = True
```

The factory rejects host-local backend identity markers such as direct Filesystem/Shell/Docker backend classes.

Production intent:

- planning files may live in a bounded state/store backend;
- project Assets stay in NODE-18;
- heavy file transforms/commands execute through NODE-21 Sandbox/NODE-25 tools;
- host repository/home directories are never mounted merely because an Agent wants file tools.

---

## 15. StateBackend acceptance boundary

The real current Deep Agents integration uses StateBackend **only as a compatibility smoke fixture**.

It proves the installed Deep Agents package still accepts the current factory/backend/checkpointer/subagent contract.

It is not evidence that arbitrary state-backed virtual files are the final production Asset architecture.

Large design media must remain references, not virtual text files in graph state.

---

## 16. Durable checkpointer

`DeepAgentCheckpointerProvider` supplies the checkpointer used by `create_deep_agent`.

A compiled Deep Agent without a checkpointer is rejected.

Production composition should reuse NODE-28's official PostgreSQL checkpointer lifecycle.

This keeps Deep Agent planning/subagent state restart-safe rather than tied to one process.

---

## 17. Store boundary

An optional `DeepAgentStoreProvider` may supply a LangGraph/Deep Agents store.

The store is trusted composition state, not a place for provider credentials.

If the installed Deep Agents factory does not support the required store parameter while a store was explicitly requested, NODE-29 fails closed rather than silently dropping persistence semantics.

---

## 18. Current create_deep_agent contract

`DeepAgentRuntimeFactory` loads the installed `deepagents.create_deep_agent` dynamically and inspects the current signature.

NODE-29 requires support for:

```text
model
tools
system_prompt
subagents
backend
checkpointer
```

If one of those capabilities is missing, compilation fails with a normalized factory error.

This makes a breaking Deep Agents upgrade visible in CI instead of silently changing LUMI runtime semantics.

---

## 19. Production factory is bounded

The raw `DeepAgentRuntimeFactory` is an internal implementation primitive.

The public production API exports:

```text
BoundedDeepAgentRuntimeFactory
```

which always wraps the result in `LimitedCompiledDeepAgent`.

The static validator uses AST import/export inspection to guarantee the unbounded raw factory is not exported from the package public API.

---

## 20. NODE-28 integration

`DeepAgentControlPlaneCompiler` compiles an exact Deep Agent definition and verifies:

```text
graph_key
graph_version
agent_config_version
deep_agent_definition_hash
```

match the immutable definition.

It then builds:

```text
GraphRegistry
DurableCompiledGraphRegistry
```

for NODE-28.

If a durable graph catalog verifier is supplied, the NODE-28 GraphDefinition must already match the admin-installed catalog entry before traffic is accepted.

---

## 21. Planning behavior

Deep Agents' built-in planning behavior may be enabled by definition.

`planning_enabled` is stored in immutable runtime provenance.

P0 does not expose a second planning database; the durable LangGraph state/checkpoint remains execution state.

Product task truth remains the LUMI Task/AgentRun model.

---

## 22. Virtual files

`virtual_files_enabled` is immutable runtime provenance.

Even when enabled:

- virtual files are not authoritative project Assets;
- binary media should use Asset refs;
- file content must remain bounded;
- execution must not imply host filesystem access.

A production backend adapter can route durable text workspace operations to controlled storage while heavy processing goes through Sandbox.

---

## 23. Cost behavior

Every root/subagent model is expected to be NODE-22-bound, so model usage flows through NODE-27 accounting.

Every external tool write remains NODE-25/NODE-20-bound.

Delegation does not create a billing exemption.

A child may use a cheaper model profile if configured, but cannot silently change hard quality constraints outside normal Model Gateway routing policy.

---

## 24. Cancellation and retries

Deep Agents does not own external side-effect correctness.

If a graph node retries:

- model calls use NODE-20/NODE-22 paid invocation guard;
- Tool Gateway writes use the stable framework tool-call idempotency key;
- Sandbox/worker operations use their own cancellation checkpoints.

Graph cancellation does not erase provider costs already incurred.

---

## 25. Security scan

NODE-29 statically scans:

```text
apps/agent-runtime/src/lumi_agent_runtime/deep_runtime
```

for ambient authority.

Forbidden direct imports include examples:

- asyncpg/SQLAlchemy/psycopg;
- provider SDKs;
- requests;
- Docker;
- subprocess;
- cloud/provider secret markers;
- Docker socket.

The Deep Runtime composes trusted ports instead of importing those capabilities directly.

---

## 26. Real current-library acceptance

### Deep Agents factory smoke

```text
scripts/integration_deep_agents_runtime.py
```

Uses:

- current `create_deep_agent`;
- current StateBackend API as a test-only backend;
- LangChain BaseChatModel test double marked as NODE-22-bound;
- one leaf subagent definition;
- LangGraph InMemorySaver;
- bounded compiled graph.

The model returns deterministic marker:

```text
NODE29_DEEP_AGENT_OK
```

No external credential is needed.

### LangChain ToolCall injection smoke

```text
scripts/integration_deep_agent_tool_gateway.py
```

Verifies:

- model-facing schema includes payload;
- model-facing schema excludes `tool_call_id`;
- framework ToolCall ID is injected at execution;
- stable ToolCall ID becomes stable NODE-25 idempotency key.

---

## 27. Unit acceptance

Tests cover:

- child tool escalation rejected;
- definition hash changes when child scope changes;
- delegation limits bounded;
- binary metadata rejected;
- unmarked model rejected;
- ToolProvider scope expansion rejected;
- nested subagent delegation fails closed in P0;
- recursion/concurrency limits cannot be widened;
- stable tool-call ID produces stable idempotency key;
- subagent parent scope forwarded to Tool Gateway.

---

## 28. CI

Dedicated workflow:

```text
.github/workflows/deep-agents-runtime.yml
```

Sequential gates:

### deep-contract

- compile NODE-29 runtime;
- revalidate NODE-25 Tool Gateway;
- revalidate NODE-28 control plane;
- NODE-29 static architecture contract;
- dependency-free unit tests that do not require the live Deep Agents package.

### deep-quality

- frozen workspace install;
- current Deep Agents package import/signature smoke;
- current Deep Agents integration;
- current LangChain ToolCall injection integration;
- pytest;
- Ruff;
- Pyright.

### deep-stack

- re-run NODE-28 current LangGraph integration;
- compile a NODE-29 graph bundle into NODE-28 registries;
- prove exact definition hash/version provenance;
- no live provider/tool credential required.

Hosted PASS is not claimed until real runners execute these jobs green.

---

## 29. P0 limitations

Intentionally deferred:

1. nested subagent delegation beyond root→leaf;
2. durable counter for every subagent task invocation;
3. production concrete virtual-file backend implementation;
4. provider-specific LangChain model adapter code in this package;
5. arbitrary remote tool registration;
6. host-local filesystem/shell backend;
7. public plugin-defined subagent code;
8. dynamic model/tool permission widening;
9. unbounded parallel subagents;
10. customer billing logic.

These are explicit boundaries, not hidden omissions.

---

## 30. Definition of Done boundary

NODE-29 implementation scope is:

```text
immutable Deep Agent definition
+ root/child scope compiler
+ NODE-22 model boundary
+ NODE-25 tool boundary
+ stable ToolCall idempotency
+ trusted backend/checkpointer ports
+ bounded create_deep_agent factory
+ current Deep Agents compatibility integration
+ NODE-28 graph compiler
+ deterministic tests
+ docs
+ CI
```

The node remains:

```text
IMPLEMENTED / VALIDATING / not COMPLETE
```

until required hosted jobs receive a runner and execute green.
