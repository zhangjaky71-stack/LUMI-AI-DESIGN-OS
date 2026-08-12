# NODE-29 — Deep Agents Runtime

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-21, NODE-25, NODE-28, NODE-30/31 contracts  
> Produces: LUMI Deep Agent factory、filesystem/sandbox backend、subagent/skills/context policy

---

## 1. 目标

在 LangGraph 控制面内提供“自主完成复杂子任务”的 Agent Harness。Deep Agents 当前提供 planning/todo、filesystem context、subagents、memory、skills、context compaction 与 sandbox integration，LUMI 使用这些能力但保持平台权限边界。

## 2. Placement

```text
LangGraph Agentic Node
      ↓
LumiDeepAgentFactory
      ↓
create_deep_agent(...)
      ↓
Tools via Tool Gateway
Filesystem via scoped backend
Subagents via Agent Registry
Skills via Skill Registry
```

Deep Agent 不直接决定 Project 最终 lifecycle。

## 3. Agent Factory

输入：

```text
agent_config_version
organization_id
project_id
agent_run_id
task_id
context_bundle_ref
budget
permission_scope
```

输出可 invoke/stream 的 Agent instance。

## 4. Planning / Todo

保留 Deep Agents built-in planning，但 Todo 是 agent scratch execution plan；项目业务 Task Graph 仍在 DB。

需要把重要 Todo/plan summary 投影到 Task/Run timeline，但不要让 todo list 成业务真相源。

## 5. Filesystem

虚拟路径：

```text
/workspace/input   read-only references/materialized files
/workspace/work    agent scratch
/workspace/output  candidate outputs
/memory            scoped memory backend
/skills            read-only skill materialization
```

backend 可映射 Sandbox/Store；权限按 agent config。

## 6. Context Offloading

大 tool result 写文件/ref，只向模型返回摘要和路径。自动 compaction 允许使用，但关键 Project facts/constraints 必须来自 Context Compiler 的 pinned block，不能因 summary 被遗忘。

## 7. Subagents

用途：context isolation + specialized expertise。

P0：

```text
researcher
creative-specialist
critic
```

实际名称由 Agent Registry resolve。

长期并行/可取消工作不要只靠同步 subagent；进入 TaskGraph + LangGraph orchestration。

## 8. Tool Access

Deep Agent 只得到 Tool Gateway wrapper tools。每个 tool call 自动注入 tenant/run/task scope，不允许模型提供另一个 organization_id 绕权。

## 9. Shell

只有绑定 SandboxBackend 的 agent 才能得到 execute；execute 不是本机 shell。默认 Agent 没有 execute，只有确需代码/媒体处理的角色开启。

## 10. Memory

Deep Agents long-term memory 接 LUMI Memory backend/Store abstraction。Agent 不可任意写 Organization 全局 memory；write scope 由 policy 限制。

## 11. Skills

Skill materialization 按任务动态选择，不把全部 skills 永远塞 system prompt。加载 exact version，并写 provenance。

## 12. System Prompt Layers

```text
Platform safety/base
+ Agent role
+ Tool/permission policy summary
+ Task context
+ Project/Brand pinned constraints
+ selected skills
```

用户内容明确标 source，防 prompt injection 把资料文本升级成 system instruction。

## 13. Model

Agent 不直接 provider model string；使用 Model Gateway compatible model/client adapter + routing profile。必要时 reasoning role 可声明 quality class。

## 14. Budget

每次模型/工具调用通过 run budget meter。接近阈值时 agent 收到 compact warning；超限由 server policy 阻断，不靠模型自觉。

## 15. Output Contract

每个 agentic node 要求 structured task result：

```text
status
summary
decisions
artifact_refs
knowledge_refs
proposed_operations
open_questions
confidence
```

禁止用自由文本作为唯一机器输入给下一节点。

## 16. Tests

- scoped filesystem；
- subagent spawn permission；
- forbidden tool；
- context compaction 后 pinned facts retained；
- sandbox execute isolation；
- memory write scope；
- skill version loading；
- budget exhaustion；
- structured output failure repair。

## 17. 验收标准

- [ ] Deep Agent 在 LangGraph node 中运行。
- [ ] planning/subagents/filesystem/skills 可用。
- [ ] execute 只在 Sandbox。
- [ ] Tool Gateway 权限不被绕过。
- [ ] Context compaction 不丢 hard constraints。
- [ ] structured output 可消费。

## 18. Definition of Done

```text
deep-agent factory implemented
+ sandbox/backend integration green
+ permission/context tests green
+ sample autonomous task eval green
```

下一节点：NODE-30 Agent Registry。
