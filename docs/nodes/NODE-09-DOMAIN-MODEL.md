# NODE-09 — Domain Model

> Phase: 1 Domain / Contract  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-01, NODE-06  
> Produces: 领域边界、聚合、实体、值对象、状态机和跨域规则

---

## 1. 目标

在写数据库和 API 前定义“系统里到底有什么”。Domain Model 是数据库、API、事件、Agent State 与前端 UI 的共同语义基础，但不等于 ORM model。

## 2. Bounded Contexts

```text
Identity & Tenancy
Workspace / Project
Brand
Asset
Design
Artifact & Version
Agent Execution
Workflow / Task
Generation / Provider
Billing / Cost
Collaboration
Audit / Governance
```

跨 context 只能通过明确 ID/contract/event 连接，禁止 import 对方 ORM 内部实现形成循环依赖。

## 3. ID 策略

业务对象统一使用 application-generated UUIDv7（或经 ADR 批准的等价可排序 128-bit ID）。

规则：

- 不向前端暴露数据库自增 ID。
- `id` 全局唯一。
- 日志、事件、Trace 使用同一 ID 可关联。
- provider-native id 另存，不替代 domain id。

## 4. 核心 Aggregate

### Organization

```text
Organization
├─ id
├─ name
├─ slug
├─ status
├─ plan
└─ settings
```

所有真实业务对象必须可追溯 `organization_id`。

### Workspace

Organization 下的协作容器；P0 可一组织一个 default workspace，但 schema 不写死 1:1。

### Project

```text
Project
├─ id
├─ organization_id
├─ workspace_id
├─ name
├─ brief
├─ status
├─ active_branch_id
├─ brand_id?
└─ settings
```

状态：

```text
DRAFT → ACTIVE → ARCHIVED
          ↓
        PAUSED
```

### Brand

```text
Brand
├─ profile
├─ palettes
├─ typography
├─ logos
├─ tone
├─ visual_rules
└─ forbidden_rules
```

Brand Memory 与 Brand Rules 不是同一对象：Memory 是知识；Rules 是机器约束。

### Asset

用户上传或外部导入的原始/参考资源。

```text
Asset
├─ storage object
├─ media metadata
├─ source
├─ rights
├─ semantic metadata
└─ derived previews
```

### DesignDocument

一个结构化可编辑设计文档，内容由 Design IR 表达。

### Artifact

一次可交付/可引用结果，如 PNG、视频、SVG、PDF、DesignDocument snapshot。

### ArtifactVersion / Branch

管理 lineage、fork、compare、restore。

### AgentRun

一次 Agent runtime 执行实例。

```text
AgentRun
├─ project
├─ thread_id
├─ graph_version
├─ agent_config_version
├─ status
├─ budget
├─ usage
└─ trace refs
```

### Task

项目工作 DAG 中的可调度单元。

### Generation

一次外部 AI 模型生成/编辑请求的领域记录；与 AgentRun 分离。

### CostEntry

不可变 Ledger entry，记录 provider cost/customer usage。

## 5. Value Objects

必须定义：

```text
Money(amount_decimal, currency)
Dimensions(width, height, unit)
Point(x, y)
Rect(x, y, width, height)
Transform
Color
MimeType
StorageRef
ProviderRef
ModelRef
VersionRef
Usage
Budget
RightsPolicy
```

Money 永远不用 float。

## 6. 关键区别

### Asset vs Artifact

- Asset：作为输入、素材或外部资源。
- Artifact：系统任务产生或版本化管理的成果。
- 同一个文件可通过 lineage 由 Asset 派生 Artifact，但 domain role 不混淆。

### Project State vs LangGraph State

- Project State：业务真相。
- LangGraph State：执行上下文/checkpoint。
- LangGraph 不拥有 Project 生命周期真相。

### Memory vs Knowledge

- Memory：用户/项目/Agent 的经验性持续信息。
- Knowledge：可检索资料库和外部/上传事实来源。

## 7. 状态机

### AgentRun

```text
PENDING
→ RUNNING
→ WAITING_USER
→ RUNNING
→ SUCCEEDED

RUNNING → FAILED
RUNNING → CANCEL_REQUESTED → CANCELLED
RUNNING → PAUSED → RUNNING
```

### Task

```text
PENDING
→ READY
→ RUNNING
→ SUCCEEDED

RUNNING → WAITING_USER
RUNNING → WAITING_DEPENDENCY
RUNNING → FAILED
PENDING/RUNNING → CANCELLED
```

### ArtifactVersion

```text
DRAFT → READY → APPROVED
  │       │
  └──────→ REJECTED
```

不要删除历史 approved version；创建新 version。

## 8. Domain Invariants

1. 任何 Project/Asset/Artifact/Task 必须属于一个 Organization。
2. 用户访问对象前必须通过 tenant membership。
3. Artifact parent 不能形成环。
4. Task dependency graph 不能形成环。
5. Cost Ledger entry 创建后不原地修改金额，调整用 reversal/adjustment entry。
6. Approved version 不被原地覆盖。
7. Hard Constraint 不能在没有 override audit 的情况下被忽略。
8. Paid side effect 必须有 operation/idempotency identity。
9. Storage object 必须有 checksum 和 ownership metadata。
10. Provider error 不直接成为 domain status；先 normalize。

## 9. Domain Services

预定义服务边界：

```text
ProjectService
BrandPolicyService
DesignOperationService
ArtifactVersionService
TaskGraphService
GenerationService
CostLedgerService
ApprovalService
AccessPolicyService
```

这些服务实现业务规则，不把规则散落在 HTTP handler。

## 10. Repository Interfaces

Domain 依赖 abstract repository，而非 SQLAlchemy Session：

```text
ProjectRepository
AssetRepository
ArtifactRepository
TaskRepository
AgentRunRepository
CostLedgerRepository
```

P0 不做教条式完整 DDD，但要保持 domain rule 与 persistence 解耦。

## 11. Domain Events

候选：

```text
project.created
asset.ready
agent_run.started
agent_run.waiting_user
artifact.version_created
artifact.approved
task.succeeded
generation.completed
cost.recorded
```

事件 envelope 到 NODE-12 定义。

## 12. 输出

- `docs/domain/DOMAIN-MODEL.md`
- `packages`/Python domain types skeleton
- state transition tests
- entity relationship diagram

## 13. 验收标准

- [ ] 所有 P0 业务对象有唯一职责。
- [ ] Asset/Artifact/DesignDocument/Version 区分清楚。
- [ ] LangGraph State 与 Domain State 分离。
- [ ] 状态机与不变量有测试表达。
- [ ] organization_id 贯穿所有租户业务对象。
- [ ] 不含 ORM/HTTP provider 细节污染 domain。

## 14. Definition of Done

```text
domain glossary frozen
+ aggregates/state machines documented
+ invariants testable
+ bounded contexts mapped
```

下一节点：NODE-10 Database Schema。
