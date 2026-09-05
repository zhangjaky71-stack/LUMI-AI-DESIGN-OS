# NODE-09 — Domain Model

> Phase: 1 Domain / Contract  
> Status: **IMPLEMENTED / VALIDATING**  
> Priority: P0  
> Depends on: NODE-01, NODE-06; stacked implementation currently includes accepted NODE-08 head  
> Produces: 领域边界、聚合、实体、值对象、状态机和跨域规则  
> Implementation: `services/domain/src/lumi_domain`  
> Tests: `services/domain/tests/test_domain_model.py`  
> Domain Reference: `docs/domain/DOMAIN-MODEL.md`  
> Acceptance: `reports/nodes/NODE-09/acceptance.md`  
> Stacked PR: `#7`

---

## 1. 目标

在写数据库和 API 前定义“系统里到底有什么”。Domain Model 是数据库、API、事件、Agent State 与前端 UI 的共同语义基础，但不等于 ORM model。

NODE-09 的工程实现明确保持：

```text
Domain != ORM
Domain != HTTP DTO
Domain != LangGraph checkpoint
Domain != Pixi scene graph
Domain != provider SDK types
```

## 2. Bounded Contexts

机器可读 `BoundedContext` 已冻结 12 个 context：

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

业务对象统一使用 application-generated UUIDv7。

实现：

```text
lumi_domain.ids.new_uuid7()
```

规则：

- 不向前端暴露数据库自增 ID；
- `id` 全局唯一；
- 日志、事件、Trace 可用同一 domain ID 关联；
- provider-native id 另存 `ProviderRef`，不替代 domain id；
- UUIDv7 生成不依赖数据库或第三方 package。

## 4. 核心 Aggregate / Entity

已实现语义骨架：

```text
Organization
Workspace
Project
Brand
Asset
DesignDocument
Artifact
ArtifactVersion
ArtifactBranch
AgentRun
Task
Generation
CostEntry
```

### Organization

Tenant ownership root。

### Workspace

Organization 下协作容器；schema 不写死 organization/workspace 1:1。

### Project

```text
Project
├─ organization_id
├─ workspace_id
├─ name
├─ brief
├─ status
├─ active_branch_id?
├─ brand_id?
└─ settings
```

### Brand

```text
Brand
├─ profile
├─ palettes
├─ typography
├─ logo_asset_ids
├─ tone
├─ visual_rules
└─ forbidden_rules
```

Brand Memory 与 Brand Rules 仍是不同概念：Memory 是知识/经验；Rules 是机器约束。

### Asset

用户上传或外部导入的输入/参考资源。`StorageRef.owner_organization_id` 必须与 Asset tenant 一致。

### DesignDocument

结构化可编辑设计文档身份；后续内容由 Design IR 表达。绝不持久化 Pixi scene tree 作为文档真相。

### Artifact / ArtifactVersion / ArtifactBranch

- Artifact：可交付/可引用成果身份；
- ArtifactVersion：不可原地覆盖的版本节点；
- ArtifactBranch：指向某个 version head 的工作分支。

### AgentRun

一次 Agent runtime 的业务执行记录，与 LangGraph State/Checkpoint 分离。

### Task

项目工作 DAG 的可调度单元。

### Generation

一次规范化 AI model generation/edit 领域记录，与 AgentRun 分离；付费请求必须绑定 `OperationIdentity`。

### CostEntry

不可变 Ledger entry；修正通过 reversal/adjustment 新 entry 完成。

## 5. Value Objects

已实现：

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
OperationIdentity
NormalizedProviderError
```

关键约束：

- Money 永远不用 float；
- StorageRef 必须有 SHA-256 checksum 与 owner organization；
- OperationIdentity 必须同时包含 domain operation id 与 idempotency key；
- Provider Error 在进入领域状态前必须 normalize。

## 6. 关键区别

### Asset vs Artifact

- Asset：输入、素材或外部资源；
- Artifact：系统任务产生或版本化管理的成果；
- lineage 可以连接二者，但 domain role 不混淆。

### DesignDocument vs ArtifactVersion

- DesignDocument：可编辑结构化设计身份；
- ArtifactVersion：不可变成果/version lineage 节点。

### Project State vs LangGraph State

- Project State：业务真相；
- LangGraph State：执行上下文/checkpoint；
- LangGraph 不拥有 Project 生命周期真相。

### Memory vs Knowledge

- Memory：用户/项目/Agent 的经验性持续信息；
- Knowledge：可检索资料库和外部/上传事实来源。

## 7. 状态机

### Project

```text
DRAFT → ACTIVE → ARCHIVED
          ↓ ↑
        PAUSED
```

实现另外允许业务归档仍处于 DRAFT/PAUSED 的项目；ARCHIVED terminal。

### AgentRun

```text
PENDING
→ RUNNING
→ WAITING_USER
→ RUNNING
→ SUCCEEDED

RUNNING → FAILED
RUNNING/WAITING_USER/PAUSED → CANCEL_REQUESTED → CANCELLED
RUNNING → PAUSED → RUNNING
```

### Task

```text
PENDING → READY → RUNNING → SUCCEEDED
RUNNING → WAITING_USER → RUNNING
RUNNING → WAITING_DEPENDENCY → READY
RUNNING → FAILED → READY
cancel transitions are explicitly bounded
```

### ArtifactVersion

```text
DRAFT → READY → APPROVED
  │       │
  └──────→ REJECTED
```

APPROVED / REJECTED 为 terminal。Approved version 不原地覆盖；创建新 version/branch。

## 8. Domain Invariants

已编码并写入测试：

1. Tenant business entities 必须暴露 `organization_id`。
2. 用户访问对象前必须通过 tenant membership。
3. Artifact lineage 不能形成环。
4. Task dependency graph 不能形成环。
5. Cost Ledger entry 创建后不可原地修改；metadata 也深度只读；调整用 reversal/adjustment entry。
6. Approved version 不被原地覆盖或 revised。
7. Hard Constraint 不能在没有 override audit 的情况下被忽略。
8. Paid side effect 必须有 operation/idempotency identity。
9. Storage object 必须有 SHA-256 checksum 和 ownership metadata，且 Asset/Storage tenant 一致。
10. Provider error 不能直接成为 domain status；先通过 provider-agnostic normalizer。

## 9. Domain Services / Ports

预定义 Protocol 边界：

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

这些服务承载业务规则，不把规则散落在 HTTP handler。

## 10. Repository Interfaces

Domain 依赖 abstract Protocol，而非 SQLAlchemy Session：

```text
ProjectRepository
AssetRepository
ArtifactRepository
TaskRepository
AgentRunRepository
CostLedgerRepository
```

NODE-10 以后提供 adapter；`lumi_domain` 不引入 ORM。

## 11. Domain Events

语义词汇已冻结：

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

事件 envelope/version/delivery 由 NODE-12 定义。

## 12. 工程输出

- [x] `docs/domain/DOMAIN-MODEL.md`
- [x] `services/domain/src/lumi_domain`
- [x] state transition tests
- [x] invariant tests
- [x] Mermaid bounded-context map
- [x] Mermaid semantic ER diagram
- [x] static forbidden-dependency boundary test
- [x] `reports/nodes/NODE-09/acceptance.md`

## 13. 验收标准

- [x] 所有 P0 业务对象有唯一职责并已映射。
- [x] Asset/Artifact/DesignDocument/Version/Branch 区分清楚。
- [x] LangGraph State 与 Domain State 分离。
- [x] 状态机与不变量有测试表达。
- [x] `organization_id` 贯穿 tenant business entities。
- [x] Domain source 不设计 ORM/HTTP/provider implementation 类型。
- [ ] Ruff format/lint 真实 runner PASS。
- [ ] Pyright 真实 runner PASS。
- [ ] Pytest 真实 runner PASS。
- [ ] Existing contracts/regression/security gates 真实 runner PASS。

当前未完成项由 GitHub hosted runner provisioning 故障阻塞：workflow 可在 `runner_id=0 / steps=[]` 状态下在执行任何 step 前失败。该外部故障不计为代码 PASS 或 FAIL。

## 14. Definition of Done

```text
domain glossary frozen                         IMPLEMENTED
aggregates/state machines documented           IMPLEMENTED
invariants executable                          IMPLEMENTED
bounded contexts mapped                        IMPLEMENTED
framework/provider boundary enforced by test   IMPLEMENTED
real CI validation                             BLOCKED_EXTERNAL
```

工程状态：**IMPLEMENTED / VALIDATING**。

真实 CI 全绿后才能改为 `COMPLETE`，随后进入 **NODE-10 — Database Schema**。
