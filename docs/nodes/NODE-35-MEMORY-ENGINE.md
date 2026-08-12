# NODE-35 — Memory Engine

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / QUALITY  
> Depends on: NODE-34, NODE-16, NODE-10  
> Produces: Session/User/Project/Brand/Agent/Organization Memory、写入候选与检索/合并机制

---

## 1. 目标

让 LUMI 在跨对话/跨任务中记住真正有价值的信息，同时避免把所有聊天永久保存为“事实”。Deep Agents 支持长期 memory；LUMI 增加 scope、权限、置信度、版本和治理。

## 2. Memory vs Checkpoint

- LangGraph checkpoint：执行状态/短期会话。
- Memory：经过提炼、可跨 thread 使用的信息。

二者不能混为一谈。

## 3. Scopes

```text
SESSION
USER
PROJECT
BRAND
AGENT
ORGANIZATION
```

写入权限逐级收紧；普通 Agent 默认不能写 Organization memory。

## 4. Memory Record

```text
id
organization_id
scope_type
scope_id
kind
content_structured
summary
source_refs
confidence
status
created_by
created_at
last_confirmed_at
expires_at?
embedding?
version
```

## 5. Kinds

```text
PREFERENCE
FACT
DECISION
CONSTRAINT_PREFERENCE
WORKFLOW_LEARNING
EPISODIC_SUMMARY
```

硬 Brand Rule 不应只存在 memory，应同步/升级到 Brand Rules 经明确流程批准。

## 6. Write Pipeline

```text
conversation/run observation
→ memory candidate
→ classify scope/kind
→ sensitivity filter
→ dedupe/conflict
→ confidence
→ write or request confirmation
```

## 7. Explicit Memory

用户说“以后都这样”“记住这个品牌不要用蓝色”等可提升 candidate confidence，但如果涉及 Brand hard rule，转换为明确 brand rule proposal。

## 8. Conflict

新 memory 与旧事实冲突：

```text
supersede
confirm
keep both with temporal validity
```

禁止简单 embedding 最近一条覆盖。

## 9. Retrieval

先 scope filter/permission，再 hybrid relevance。优先：

```text
Project exact
Brand
User preference
Agent learned heuristic
```

根据任务调整。

## 10. Consolidation

后台 consolidation：

- 合并重复 episodic memories；
- 删除低价值过期 scratch；
- 保留 source lineage；
- 不自动提升为系统安全规则。

## 11. Privacy

敏感信息 classification：credentials、支付、健康等不进入通用 memory。提供用户查看/删除自己的可删除 memory 路径；Audit/法定 retention 分开。

## 12. Backend

P0 DB + pgvector/structured query。Deep Agents filesystem memory adapter 可把 record 映射成受控虚拟文件/Store，不把磁盘目录当唯一真相。

## 13. Tests

- scope access；
- cross-tenant isolation；
- conflict/supersede；
- explicit remember；
- sensitive deny；
- consolidation provenance；
- deletion/retention；
- context retrieval ranking。

## 14. 验收标准

- [ ] 六类 scope。
- [ ] memory write 不是聊天自动 dump。
- [ ] source/confidence/version 存在。
- [ ] conflict 有规则。
- [ ] Agent write scope 受限。
- [ ] sensitive deny tests。

## 15. Definition of Done

```text
memory repository + candidate pipeline implemented
+ Deep Agents adapter green
+ privacy/scope tests green
```

下一节点：NODE-36 Knowledge Engine。
