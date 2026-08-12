# NODE-38 — Design IR Runtime

> Phase: 5 Design Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / CORE  
> Depends on: NODE-13, NODE-14, NODE-15  
> Produces: Design IR 解析/迁移/操作执行运行时、TS/Python 一致性、命令历史与 canonical hash

---

## 1. 目标

把 NODE-13 的 Design IR V1 从“规范”变成实际可执行的跨语言 runtime。任何 Agent/Canvas/Export 修改都必须经过 Runtime，而不是直接改 JSON。

## 2. 包结构

```text
packages/design-ir/
├─ src/schema/
├─ src/runtime/
├─ src/operations/
├─ src/migrations/
├─ src/canonical/
├─ src/diff/
├─ src/fixtures/
└─ tests/

packages-py/design_ir/
├─ models/
├─ validate/
├─ operations/
├─ canonical/
└─ migrations/
```

TypeScript 为 Canvas runtime 主实现；Python 用于 Agent/服务端验证。两端必须共享 JSON Schema conformance fixtures。

## 3. Runtime API

```text
parseDocument(raw)
validateDocument(doc)
applyOperation(doc, operation)
applyBatch(doc, operations)
computeSemanticDiff(before, after)
canonicalize(doc)
hashDocument(doc)
migrate(doc, targetVersion)
queryNodes(selector)
```

所有函数对同输入必须 deterministic。

## 4. Operation Executor

操作通过 immutable/copy-on-write 语义返回新 document snapshot：

```text
current v12
+ operation SET_TEXT
→ validate expected version
→ constraint preflight hook
→ execute
→ structural validate
→ semantic diff
→ create v13 candidate
```

禁止 UI/Agent 随意 mutation persisted object。

## 5. Version Conflict

Operation 必须携带 `expected_document_version`。不一致：

```text
DESIGN_VERSION_CONFLICT
```

P0 不做隐式 CRDT merge；前端可获取最新版本后 rebase command 或让用户选择。

## 6. Batch

BATCH 全事务：

- 预检查所有目标存在；
- hard constraint 任一失败则全失败；
- 不产生半个 document version；
- operation ids 用于去重。

## 7. Semantic Query

提供 selector：

```text
by id
by role
by kind
by parent/frame
by brand_binding
by asset_binding
by locked state
```

Agent 通过 query tool 获取局部节点，不扫描整个大 JSON prompt。

## 8. Canonical Hash

明确：

- 排除 ephemeral metadata；
- object key 稳定排序；
- number normalization；
- Unicode normalization policy；
- resource refs 按 stable id；
- hash algorithm SHA-256。

同语义文档跨 TS/Python 必须生成相同 hash fixture。

## 9. Migration

每 major/minor schema升级提供纯函数迁移。迁移：

```text
v1.0 → v1.1 → v2.0
```

禁止一步随意猜。原始 version/hash/provenance 保留。

## 10. Diff

输出机器结构：

```text
nodes_added
nodes_removed
properties_changed
text_changed
geometry_changed
asset_replaced
constraints_changed
```

供 Versions UI、Critic 和 Audit 使用。

## 11. Spatial Hook

Runtime 提供 bounds/geometry helper 与 spatial index adapter interface；实际高性能索引可在 Canvas runtime 使用 RBush/自定义结构，不把索引结构持久化进 IR。

## 12. Error Model

```text
IR_SCHEMA_INVALID
IR_GRAPH_CYCLE
IR_REFERENCE_MISSING
IR_VERSION_UNSUPPORTED
IR_OPERATION_INVALID
IR_TARGET_NOT_FOUND
IR_VERSION_CONFLICT
IR_BATCH_FAILED
```

Error 带 JSON pointer/node ids，不暴露内部 stack 给 UI。

## 13. Fuzz / Property Tests

必须有 property-based tests：

- parse→serialize→parse 稳定；
- valid operation 保持结构 invariant；
- random reorder 不产生 parent cycle；
- invalid floats 拒绝；
- TS/Python canonical hash 一致。

## 14. 性能预算

普通 2k node document：

- parse/validate 不成为 UI 主线程明显卡顿；
- 单节点 operation 不全量重建不可接受的大对象；
- batch 100 ops 有 benchmark。

具体阈值由 NODE-08 机器基准记录并在实现时锁定。

## 15. 验收标准

- [ ] TS/Python conformance fixtures 全绿。
- [ ] V1 operation executor 完整。
- [ ] Batch atomic。
- [ ] canonical hash 跨语言一致。
- [ ] semantic diff 可用于 Version UI。
- [ ] migration chain 可测试。
- [ ] Agent/Canvas 不直接 mutation persisted IR。

## 16. Definition of Done

```text
runtime packages published internally
+ conformance/property tests green
+ operation benchmark recorded
```

下一节点：NODE-39 Constraint Validator。
