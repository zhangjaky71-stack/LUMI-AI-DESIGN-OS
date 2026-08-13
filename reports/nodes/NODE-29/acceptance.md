# NODE-29 Acceptance — Deep Agents Runtime

> Branch: `node-29-deep-agents-runtime`  
> Base: `node-28-langgraph-control-plane`  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

---

## 1. Architecture

Accepted execution path:

```text
DeepAgentDefinition
→ BoundedDeepAgentRuntimeFactory
→ current create_deep_agent
→ LimitedCompiledDeepAgent
→ NODE-28 DurableCompiledGraphRegistry
→ NODE-28 durable execution
```

The node does not grant provider/network/database/host-shell authority.

---

## 2. Immutable definition

- [x] root Agent key/runtime version
- [x] graph key/version
- [x] agent-config version
- [x] system prompt
- [x] model profile
- [x] root tool scope
- [x] leaf subagent definitions
- [x] delegation limits
- [x] max steps
- [x] planning/virtual-file policy
- [x] deterministic content hash

Changing a child tool scope changes the definition hash.

---

## 3. Tool non-escalation

Compile-time:

```text
child.allowed_tools ⊆ root.allowed_tools
```

Run-time:

```text
context.allowed_tools ⊆ definition.allowed_tools
```

ToolProvider output must exactly match the effective requested scope and each returned tool must carry NODE-25 binding evidence.

Subagent context forwards both child scope and parent scope to NODE-25.

---

## 4. Model boundary

All root/subagent model objects must carry:

```text
_lumi_model_gateway_bound = True
```

Unmarked model objects fail before Deep Agents factory execution.

Deep Runtime package does not import provider SDKs or provider API-key markers.

---

## 5. Backend boundary

All backend objects/factories must carry:

```text
_lumi_backend_bound = True
```

Factory rejects direct host-local backend identity markers.

StateBackend is used only by deterministic current-library smoke, not claimed as production project Asset storage.

---

## 6. Durable checkpointer

A checkpointer is required before compilation.

The compiled Deep Agent must retain a checkpointer or compilation fails.

Production composition is expected to use NODE-28's durable checkpointer lifecycle.

---

## 7. P0 delegation

- [x] root→leaf custom subagents supported
- [x] child count bounded
- [x] max graph recursion bounded
- [x] max graph concurrency bounded
- [x] nested `can_delegate=True` fails closed
- [x] caller cannot widen immutable graph limits

Nested durable delegation accounting is deferred rather than weakly approximated.

---

## 8. Stable ToolCall idempotency

Current LangChain ToolCall identity is injected into the tool wrapper rather than exposed to the model.

Expected key:

```text
deep-agent:<agent_run_id>:<tool_call_id>
```

The same framework tool-call ID generates the same NODE-25 idempotency key.

No random UUID is used as the side-effect identity.

---

## 9. NODE-25 bridge

`Node25ToolGatewayInvoker` maps trusted context to current NODE-25 contracts, including when supported:

- organization
- project
- AgentRun
- Task
- actor Agent
- exact tool version
- arguments
- purpose
- permission context
- Agent allow scope
- parent allow scope
- stable idempotency key
- trace ID

Risk/HITL/schema/offload/audit remain NODE-25 responsibilities.

---

## 10. NODE-28 provenance

`DeepAgentControlPlaneCompiler` verifies compiled GraphDefinition matches:

```text
graph_key
graph_version
agent_config_version
deep_agent_definition_hash
```

and registers the bounded compiled graph into NODE-28 exact-version registries.

Optional durable graph-catalog verification occurs before traffic acceptance.

---

## 11. Unit tests authored

```text
apps/agent-runtime/tests/test_deep_runtime_contracts.py
apps/agent-runtime/tests/test_deep_runtime_factory.py
apps/agent-runtime/tests/test_deep_runtime_tooling.py
```

Coverage includes:

- child tool escalation denied;
- content hash reacts to child scope;
- invalid delegation limits;
- binary metadata rejection;
- unmarked Model Gateway model denied;
- ToolProvider scope expansion denied;
- nested delegation denied;
- recursion/concurrency widening denied;
- stable tool-call idempotency;
- parent tool scope forwarded for child invocation.

---

## 12. Current Deep Agents integration

```text
scripts/integration_deep_agents_runtime.py
```

Authored acceptance:

- import current Deep Agents backend API;
- current `create_deep_agent` signature must support model/tools/system_prompt/subagents/backend/checkpointer;
- compile one root + one leaf subagent;
- use LangGraph checkpointer;
- invoke deterministic test model;
- receive `NODE29_DEEP_AGENT_OK`.

No live model/provider credential is required.

---

## 13. Current LangChain tool injection integration

```text
scripts/integration_deep_agent_tool_gateway.py
```

Acceptance:

- model-facing schema contains `payload`;
- model-facing schema does not contain `tool_call_id`;
- framework ToolCall ID is available at execution;
- stable ID becomes stable Tool Gateway idempotency key.

---

## 14. Static architecture contract

CI uses:

```text
scripts/validate_deep_agents_runtime_contract_v2.py
```

It verifies:

- immutable runtime/subagent contract;
- tool non-escalation;
- bounded public factory;
- current create_deep_agent capability signature requirements;
- Model/Tool/Backend trusted markers;
- stable injected ToolCall identity;
- NODE-25 adapter fields;
- NODE-28 compiler provenance;
- no provider/DB/network/host-shell ambient authority;
- real integration fixtures exist.

The earlier `validate_deep_agents_runtime_contract.py` is not used by CI because its export-name substring check was intentionally replaced by AST inspection in v2.

---

## 15. CI

Dedicated workflow:

```text
.github/workflows/deep-agents-runtime.yml
```

Required jobs:

1. `deep-contract`
2. `deep-quality`
3. `deep-stack`

No hosted PASS is claimed until jobs actually execute on a runner.

---

## 16. Status discipline

Previous stacked nodes have repeatedly encountered a GitHub Actions account billing/spending-limit blocker.

NODE-29 must inspect its own workflow after the Draft PR is created.

If the first required job has:

```text
steps=[]
runner_id=0
billing/spending annotation
```

classification is:

```text
IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE
```

If a runner starts and tests fail, that is a NODE-29 engineering defect until fixed.

---

## 17. Explicit deferred scope

Not claimed by NODE-29:

- nested subagent delegation beyond root→leaf;
- durable per-delegation counter across nested trees;
- final production virtual-file backend implementation;
- direct provider-specific LangChain adapter code in Deep Runtime;
- arbitrary tool/function registration bypassing NODE-25;
- host filesystem/shell backend;
- customer billing.

---

## 18. Definition of Done status

Implementation scope authored:

```text
immutable Deep Agent definition
+ bounded factory
+ model boundary
+ tool boundary
+ stable write idempotency
+ child permission narrowing
+ backend/checkpointer ports
+ current Deep Agents integration
+ current LangChain ToolCall integration
+ NODE-28 compilation
+ tests/docs/CI
```

**COMPLETE remains false until hosted required gates execute green.**
