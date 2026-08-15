# NODE-09 — Domain Model

> Phase: 1 Domain / Contract  
> Status: **VALIDATING**  
> Implementation Status: **IMPLEMENTED / REPOSITORY CI PENDING**  
> Implementation Branch: `feat/node-09-domain-model`  
> Acceptance Report: `reports/nodes/NODE-09/acceptance.md`  
> Canonical Domain Contract: `docs/domain/DOMAIN-MODEL.md`  
> Implemented At: `2026-08-16`  
> Priority: P0  
> Depends on: NODE-01, NODE-06  
> Produces: 领域边界、聚合、实体、值对象、状态机和跨域规则

---

## 1. 目标

在写数据库和 API 前定义“系统里到底有什么”。Domain Model 是数据库、API、事件、Agent State 与前端 UI 的共同语义基础，但不等于 ORM model。

当前实现采用纯 Python domain skeleton，放在 `apps/api/src/lumi_api/domain/`；该包只依赖 Python 标准库，不依赖 FastAPI、SQLAlchemy、Pydantic、LangGraph/LangChain、provider SDK、queue 或 object-storage SDK。

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

详细 ownership map 已冻结在 `docs/domain/DOMAIN-MODEL.md`。

## 3. ID 策略

业务对象统一使用 application-generated UUIDv7（或经 ADR 批准的等价可排序 128-bit ID）。

规则：

- 不向前端暴露数据库自增 ID。
- `id` 全局唯一。
- 日志、事件、Trace 使用同一 ID 可关联。
- provider-native id 另存，不替代 domain id。

当前实现 `lumi_api.domain.ids.new_uuid7()` 在 Python 3.12 尚无 stdlib `uuid7()` 的前提下，按 RFC UUIDv7 位布局生成 48-bit Unix 毫秒时间戳 + 随机位，并有 version/variant/time-order 测试。

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

所有真实租户业务对象必须可追溯 `organization_id`。Organization 自身的 `id` 即 tenant identity，因此不再重复存自己的 `organization_id`。

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
          ↕
        PAUSED ─→ ARCHIVED
```

### Brand

```text
Brand
├─ profile
├─ rules
└─ forbidden_rules
```

Brand Memory 与 Brand Rules 不是同一对象：Memory 是经验/知识；Rules 是机器可执行约束。

### Asset

用户上传或外部导入的原始/参考资源。

```text
Asset
├─ StorageRef(bucket/key/checksum/owner)
├─ MimeType
├─ source
├─ RightsPolicy
└─ semantic metadata
```

### DesignDocument

一个结构化可编辑设计文档，未来内容由 Design IR 表达；不等于 Pixi/Konva/Fabric runtime object。

### Artifact

一次可交付/可引用结果，如 PNG、视频、SVG、PDF、DesignDocument snapshot。

### ArtifactVersion / Branch

管理 lineage、fork、compare、restore。Approved version 是不可变历史，后续修改创建新 version。

### AgentRun

一次 Agent runtime 的业务执行记录。

```text
AgentRun
├─ project_id
├─ thread_id
├─ graph_version
├─ agent_config_version
├─ status
├─ budget
├─ usage
└─ trace refs
```

LangGraph checkpoint 是执行实现，不拥有 AgentRun/Project 业务生命周期真相。

### Task

项目工作 DAG 中的可调度单元；dependency graph 必须无环。

### Generation

一次外部 AI 模型生成/编辑请求的领域记录；与 AgentRun 分离，并必须携带 `OperationIdentity` / idempotency key。

### CostEntry

不可变 Ledger entry，记录 provider cost/customer usage。调整通过 reversal/adjustment 新 entry 表达，不改旧 entry 金额。

## 5. Value Objects

当前已实现：

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
```

核心约束：

- Money 永远不用 float，只接受 `Decimal`。
- StorageRef 必须包含 SHA-256 checksum 与 owner organization。
- Budget soft/hard limit 必须同币种，且 `soft <= hard`。
- 几何值必须 finite。
- MimeType/Color 在构造时规范化/验证。

## 6. 关键区别

### Asset vs Artifact vs DesignDocument

- Asset：作为输入、素材或外部资源。
- DesignDocument：结构化、可编辑的设计语义。
- Artifact：系统任务产生或版本化管理的可交付成果。
- ArtifactVersion：某个 Artifact 的不可变版本历史。

同一个物理文件可通过 lineage 从 Asset 派生到 Artifact，但 domain role 不混淆。

### Project State vs LangGraph State

- Project State：业务真相。
- LangGraph State：执行上下文/checkpoint。
- LangGraph 不拥有 Project 生命周期真相。
- Domain package 不 import LangGraph。

### Memory vs Knowledge

- Memory：用户/项目/Agent 的经验性持续信息。
- Knowledge：可检索资料库和外部/上传事实来源。
- Brand Rules：可执行约束，不等于 Memory/Knowledge。

## 7. 状态机

### Project

```text
DRAFT → ACTIVE → ARCHIVED
          ↕
        PAUSED ─→ ARCHIVED
```

### AgentRun

```text
PENDING
→ RUNNING
→ WAITING_USER → RUNNING
→ PAUSED → RUNNING
→ SUCCEEDED

RUNNING → FAILED
RUNNING/WAITING_USER/PAUSED → CANCEL_REQUESTED → CANCELLED
```

### Task

```text
PENDING → READY → RUNNING → SUCCEEDED
   └→ CANCELLED      ├→ WAITING_USER → READY
                     ├→ WAITING_DEPENDENCY → READY
                     ├→ FAILED
                     └→ CANCELLED
```

### ArtifactVersion

```text
DRAFT → READY → APPROVED
  │       │
  └──────→ REJECTED
```

`APPROVED` / `REJECTED` 为 terminal；不要删除或原地覆盖 approved version。

### Generation

```text
PENDING → RUNNING → COMPLETED
   └→ CANCELLED    ├→ FAILED
                   └→ CANCELLED
```

Provider-native error/state 不直接写成 domain status。

## 8. Domain Invariants

1. Workspace/Project/Brand/Asset/DesignDocument/Branch/Artifact/ArtifactVersion/AgentRun/Task/Generation/CostEntry 必须有 `organization_id`。
2. 用户访问对象前必须通过 tenant membership；通过 `AccessPolicyService` 边界实施。
3. Artifact parent lineage 不能形成环。
4. Task dependency graph 不能形成环。
5. Cost Ledger entry 创建后不原地修改金额，调整用 reversal/adjustment entry。
6. Approved version 不被原地覆盖。
7. Hard Constraint 不能在没有 override audit 的情况下被忽略；具体 engine 到 NODE-14。
8. Paid side effect 必须有 operation/idempotency identity。
9. Storage object 必须有 checksum 和 ownership metadata。
10. Provider error 不直接成为 domain status；先 normalize。
11. Cross-tenant object composition 必须由 `require_same_organization(...)` 拒绝。
12. Domain package 不允许依赖 ORM/HTTP/Agent/provider implementation package。

## 9. Domain Services

已定义协议边界：

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

Domain 依赖 abstract repository Protocol，而非 SQLAlchemy Session：

```text
ProjectRepository
AssetRepository
ArtifactRepository
TaskRepository
AgentRunRepository
CostLedgerRepository
```

NODE-10/11 的 persistence/application adapters 必须依赖这些 domain contract，而不是让 ORM model 反向定义 domain。

## 11. Domain Events

候选事件名保持冻结：

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

事件 envelope 到 NODE-12 定义；NODE-09 不提前耦合 broker/event implementation。

## 12. 输出

已实现：

```text
docs/domain/DOMAIN-MODEL.md
apps/api/src/lumi_api/domain/
├─ __init__.py
├─ entities.py
├─ errors.py
├─ ids.py
├─ invariants.py
├─ repositories.py
├─ services.py
├─ states.py
└─ value_objects.py

apps/api/tests/test_domain_model.py
reports/nodes/NODE-09/acceptance.md
reports/nodes/NODE-09/local-domain-test.txt
```

ER diagram、bounded contexts、NODE-10 translation contract 均在 `docs/domain/DOMAIN-MODEL.md`。

## 13. 测试

本地 deterministic fallback：

```bash
PYTHONPATH=. pytest -q
python -m compileall -q lumi_api tests
```

当前记录：

```text
13 passed
COMPILEALL_PASS
```

测试覆盖 UUIDv7、Money、状态机、tenant ownership、DAG/lineage 防环、approved version/cost ledger immutability、Generation normalized state、所有 tenant P0 entity 的 organization_id，以及 domain package 的 forbidden dependency scan。

Repository CI 仍必须在其固定 Python 3.12.* 环境执行 Ruff/Pyright/Pytest；本地 fallback 不能替代正式门禁。

## 14. 验收标准

- [x] 所有 P0 业务对象有唯一职责。
- [x] Asset/Artifact/DesignDocument/Version 区分清楚。
- [x] LangGraph State 与 Domain State 分离。
- [x] 状态机与不变量有测试表达。
- [x] organization_id 贯穿所有租户业务对象。
- [x] 不含 ORM/HTTP/provider/LangGraph implementation 细节污染 domain。
- [x] 本地 deterministic tests 13/13 PASS。
- [ ] Repository Python/contract/security CI PASS。
- [ ] Pull Request merged。
- [ ] `docs/NODE-INDEX.md` 更新为 COMPLETE。

## 15. Definition of Done

```text
domain glossary frozen
+ aggregates/state machines documented
+ invariants testable
+ bounded contexts mapped
+ repository CI green
+ PR merged
+ NODE index updated
```

当前状态为 `VALIDATING`，不是 `COMPLETE`。

下一节点：NODE-10 Database Schema。
