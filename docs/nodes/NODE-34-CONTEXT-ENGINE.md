# NODE-34 — Context Engine & Prompt Compiler

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE QUALITY  
> Depends on: NODE-17, NODE-30, NODE-31, NODE-35/36 contracts  
> Produces: Context Bundle、selection/ranking/compression、pinned constraints、Prompt Compiler

---

## 1. 目标

解决“Agent 知道什么、这次应该看到什么”。上下文越多不一定越好；必须按任务选择、预算、排序和压缩，而不是把所有聊天/文件塞模型。

## 2. Sources

```text
System/Agent definition
Task
Project Brief
Brand
Hard Constraints
Current Artifact/Design IR summary
Recent interaction
Memory
Knowledge retrieval
Selected Skills
Tool results
```

## 3. Context Item

```text
id
source_type
scope
trust_level
priority
content/ref
token_estimate
freshness
permissions
pinned
provenance
```

## 4. Trust

```text
SYSTEM_TRUSTED
INTERNAL_TRUSTED
USER_CONTENT
EXTERNAL_UNTRUSTED
MODEL_GENERATED
```

网页/上传文档中的“忽略之前指令”始终是 data，不升级为 trusted instruction。

## 5. Pinned Context

不可被 compaction 删除：

```text
tenant/task identity
user current instruction
hard constraints
approved brand rules
output schema
security/tool policy
budget guard
```

## 6. Token Budget

按模型 context window 和 task profile分区：

```text
base instructions
pinned facts
skills
retrieval
conversation
scratch reserve
output reserve
```

Context Builder 必须留 output/tool buffer，不把输入塞满窗口。

## 7. Selection

```text
candidate gather
→ permission filter
→ relevance scoring
→ trust weighting
→ freshness
→ dedupe
→ token packing
```

Brand/Project exact facts优先 structured source，不用 semantic memory 猜。

## 8. Compression

层次：

1. remove duplicate；
2. extract relevant spans；
3. structured summary；
4. offload full result to file/ref；
5. conversation compaction。

Summary 保存 source refs，关键事实可回查。

## 9. Artifact Context

不要把整个 Design IR 数万 nodes 直接 prompt。提供：

```text
selected nodes full detail
locked nodes
semantic outline
frame summary
nearby spatial context
asset refs
```

Agent 想看更多通过 tool query。

## 10. Prompt Compiler

输入 ContextBundle + AgentDefinition + Model capability。

输出 provider-neutral message/content blocks：

```text
system layers
trusted structured context
user instruction
untrusted references
output schema
```

Provider formatting 由 Model Gateway adapter。

## 11. Cache

可 cache：

- project summary by version；
- brand summary by version；
- skill materialization；
- retrieval results keyed query/version。

任何 permission/tenant 参与 cache key，防跨租户污染。

## 12. Context Trace

每次 model call 记录：

```text
context_bundle_id
item ids
source refs
token estimates
compression steps
```

受权限保护，不把原始敏感内容暴露普通 Admin。

## 13. Tests

- hard constraint retained under compaction；
- malicious web instruction stays untrusted；
- tenant cache isolation；
- token budget；
- large artifact selected nodes；
- stale brand version invalidates cache；
- same source dedupe。

## 14. Benchmark

比较：

```text
full dump baseline
vs selective context
```

指标：task success、constraint、tokens、latency。

## 15. 验收标准

- [ ] ContextBundle schema。
- [ ] trust/permission/pinned concept 实现。
- [ ] token budgeting。
- [ ] artifact selective context。
- [ ] Prompt Compiler 与 Provider formatting 分离。
- [ ] context trace 可解释。

## 16. Definition of Done

```text
context builder/compiler implemented
+ token/trust tests green
+ benchmark no quality regression with lower context
```

下一节点：NODE-35 Memory Engine。
