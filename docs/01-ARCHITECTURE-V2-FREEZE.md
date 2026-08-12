# LUMI AI Design OS — Architecture V2 Freeze

> **Node:** NODE-01  
> **Status:** COMPLETE / FROZEN  
> **Baseline:** LUMI AI Design OS — Architecture V2  
> **Repository:** `zhangjaky71-stack/LUMI-AI-DESIGN-OS`  
> **Purpose:** 将产品级系统的系统边界、模块边界、运行拓扑、数据拓扑、安全边界、部署边界和关键 ADR 正式冻结，作为后续代码、数据库、API、Design IR、Agent Graph 和部署工作的共同约束。

---

# 1. Architecture Freeze Decision

从 NODE-01 开始，LUMI 不再被定义为“LangChain 项目”或“AI 生图聊天机器人”，而正式定义为：

> **LUMI AI Design OS = Agent Runtime + Design Runtime + AI Infrastructure + Production Platform**

核心原则：

```text
LangGraph      = 确定性控制平面 / 生命周期 / 状态 / Checkpoint / HITL
Deep Agents    = 自主规划 / 子代理 / Skills / 长任务执行
LangChain      = 模型、工具、中间件、结构化输出等 Agent 基础能力
LangSmith      = Trace / Eval / Regression / AI 可观测
Design IR      = Agent 与设计世界之间的中间表示
Constraint     = 允许修改与禁止修改的机器可执行规则
Canvas Engine  = 可编辑设计空间
Artifact       = 生成物、版本、血缘与导出
Model Gateway  = 多模型能力、路由、降级、成本和健康管理
Tool Gateway   = 外部能力、MCP、权限和审计入口
Sandbox        = Agent 安全执行环境
Visual Critic  = 设计质量评价与修复闭环
```

任何未来实现如果绕过这些边界，默认视为架构违规，需要 ADR 批准。

---

# 2. Product Boundary

## 2.1 系统内能力

LUMI V2 负责：

- 用户、组织、Workspace、项目与权限。
- AI 对话与结构化 Design Brief。
- Research、策略、创意方向与任务规划。
- Multi-Agent 协作。
- 多模型图片、视频、文本及未来多模态能力。
- Infinite Canvas。
- Design IR / DSL。
- 局部结构化编辑。
- Design Constraint。
- Brand Kit / Brand Rules。
- Asset Library。
- Artifact / Version / Provenance。
- 视觉质量评价和自动修复。
- 导出、批量尺寸变体和项目交付。
- API 成本核算、额度和计费支撑。
- Agent/Tool/Model/Artifact 全链路 Trace 与 Audit。
- Benchmark、Regression、Release Gate。

## 2.2 外部依赖

通过 Adapter / Gateway 访问，不进入领域核心：

- LLM Provider。
- Image Provider。
- Video Provider。
- Search Provider。
- OCR / Embedding / Moderation Provider。
- Email / Payment / Analytics 等 SaaS。
- 云 Object Storage。
- 外部 MCP Server。

## 2.3 非目标

V2 首期不做：

- 自研基础大模型训练平台。
- 自研通用 GPU 云平台。
- 一开始拆成几十个微服务。
- 把所有第三方 API SDK 直接嵌入 Agent。
- 把 Canvas 前端结构作为 Agent 的数据模型。
- 用聊天历史代替 Domain Database。
- 用 LangSmith 代替业务数据库或 Artifact Version Store。

---

# 3. System Context

```text
                         ┌──────────────────────┐
                         │        USER          │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │      LUMI WEB        │
                         │ Chat / Canvas / App  │
                         └──────────┬───────────┘
                                    │ HTTPS/SSE
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                         LUMI BACKEND                            │
│                                                                 │
│ API ─ Project ─ Assets ─ Auth ─ Billing ─ Agent Control        │
│                         │                                       │
│                         ▼                                       │
│                 LangGraph / Deep Agents                         │
│                         │                                       │
│      ┌──────────────────┼──────────────────────┐                │
│      ▼                  ▼                      ▼                │
│ Model Gateway       Tool Gateway         Design Runtime         │
│      │                  │                      │                │
└──────┼──────────────────┼──────────────────────┼────────────────┘
       │                  │                      │
       ▼                  ▼                      ▼
 AI Providers       MCP / External APIs     Worker / Renderer
```

---

# 4. Architecture Style

## 4.1 首期：Modular Monolith + Specialized Workers

业务 API 首期采用模块化单体，而不是微服务爆炸：

```text
apps/api
├── auth
├── organizations
├── projects
├── assets
├── artifacts
├── canvas
├── brands
├── agent_runs
├── billing
├── audit
└── admin
```

独立部署的重负载或安全边界服务：

```text
apps/agent-runtime
apps/worker-media
services/model-gateway
services/tool-gateway
services/sandbox-runtime
```

## 4.2 拆服务的触发条件

只有满足以下条件之一才拆：

1. 独立安全边界。
2. 独立伸缩模型。
3. 独立资源模型（GPU / CPU / Browser / Sandbox）。
4. 故障必须隔离。
5. 独立发布频率已经产生明确收益。

---

# 5. Technology Baseline

> 版本号不在 NODE-01 硬编码；NODE-02 通过 lockfile 和 compatibility matrix 固定实际版本。

## 5.1 Frontend

- TypeScript。
- React ecosystem。
- Next.js 作为 Web application shell。
- PixiJS 作为高性能 Canvas renderer 首选。
- DOM overlay 处理复杂文本输入、编辑器控件与可访问性 UI。
- Zustand 类轻量 client state；服务端数据采用 query cache 模式。
- P1 协作层引入 Yjs/CRDT 抽象；P0 不让 CRDT 侵入 Design IR Domain Model。

## 5.2 Backend / Agent

- Python 作为 API / Agent Runtime 主语言。
- FastAPI 类 ASGI API 层。
- LangGraph 作为 Agent Control Plane。
- Deep Agents 作为自主 Agent harness。
- LangChain 作为模型/工具抽象层。
- Pydantic / JSON Schema 作为结构化合同基础。

## 5.3 Data

- PostgreSQL：业务真相源、任务、版本、Ledger、审计。
- PostgreSQL vector extension：P0 Memory/Knowledge/Asset embedding；容量或召回要求出现明确瓶颈后再拆专用 Vector DB。
- Redis：cache、ephemeral locks、rate limit、realtime coordination。
- S3-compatible Object Storage：图片、视频、工程文件、导出包。
- Outbox Table：可靠 Domain Event 发送。

## 5.4 Jobs / Events

P0：

```text
PostgreSQL Transaction
        ↓
Outbox
        ↓
Dispatcher
        ↓
Redis-backed Queue / Stream abstraction
        ↓
Workers
```

不把 Agent 工作流和媒体渲染工作流混成同一队列。

P1 如吞吐/事件治理成为瓶颈，可把 Event Adapter 替换为 NATS JetStream / 云消息服务，领域代码保持不变。

## 5.5 Infrastructure

- Docker / Docker Compose：本地与单机环境。
- OCI container image。
- GitHub Actions：CI/CD。
- P0 Staging 可以容器化单集群运行。
- Production 支持 Kubernetes，但在负载尚未需要时不强制引入。
- IaC 在 Deployment Node 固定。

---

# 6. Runtime Topology

```text
Browser
   │
   ├──── HTTPS REST ──────────────────────────┐
   │                                          ▼
   └──── SSE / Realtime ────────────────┐   API Service
                                        │      │
                                        │      ├── PostgreSQL
                                        │      ├── Redis
                                        │      ├── Object Storage
                                        │      │
                                        │      ▼
                                        │ Agent Runtime
                                        │      │
                                        │      ├── LangGraph
                                        │      ├── Deep Agents
                                        │      ├── Context Compiler
                                        │      └── Prompt Compiler
                                        │             │
                                        │      ┌──────┴─────────┐
                                        │      ▼                ▼
                                        │ Model Gateway     Tool Gateway
                                        │      │                │
                                        │      ▼                ▼
                                        │ AI Providers      MCP / APIs
                                        │
                                        │       Domain Event / Job
                                        │               │
                                        └───────────────▼
                                                   Worker Media
                                                       │
                                            FFmpeg / ImageMagick /
                                             render / transform
```

规则：

- API Service 不执行重媒体任务。
- Browser 不直接访问第三方模型 Provider。
- Agent 不直接拥有第三方 Provider Secret。
- 模型调用统一走 Model Gateway。
- 外部行动统一走 Tool Gateway 或 Side Effect Gateway。
- 生成的二进制资产不存 PostgreSQL，存 Object Storage；数据库只存 metadata、URI 和 provenance。

---

# 7. Agent Topology

```text
                    LUMI DIRECTOR
                         │
              LangGraph Control Graph
                         │
          ┌──────────────┼───────────────┐
          ▼              ▼               ▼
      deterministic  autonomous      approval
        nodes         deep-agent      interrupts
                         │
            ┌────────────┼──────────────┐
            ▼            ▼              ▼
        Research      Creative       Production
        Subagent      Subagent        Subagent
            │            │              │
            ▼            ▼              ▼
          Skills       Skills         Skills
```

## 7.1 Director 责任

- 解析当前 Project / Task 状态。
- 选择 Recipe。
- 初始化 Task Graph。
- 决定 deterministic node 或 autonomous node。
- 分配预算。
- 触发 Human Approval。
- 决定失败恢复路径。

## 7.2 Specialized Agents

冻结首批角色：

1. Brief Agent
2. Research Agent
3. Brand Strategy Agent
4. Creative Director Agent
5. Moodboard Agent
6. Copywriting Agent
7. Typography Agent
8. Layout Agent
9. Image Agent
10. Image Edit Agent
11. Product Render Agent
12. Video Agent
13. Critic Agent
14. Brand Consistency Agent
15. Identity Agent
16. Export Agent

## 7.3 Agent Isolation Rule

每个 Agent 通过配置获得：

```text
allowed_models
allowed_tools
allowed_skills
context_policy
memory_policy
budget_policy
permission_policy
output_schema
benchmark_profile
```

禁止“万能 Agent”拥有所有工具和所有数据。

---

# 8. Control Plane Boundary

LangGraph 是最高级 Agent 生命周期控制器。

负责：

- Graph state。
- checkpoint / resume。
- interrupt / HITL。
- deterministic branching。
- retry policy integration。
- long-running run state。
- thread/run mapping。

Deep Agents 被当作 Graph 中的自主执行单元，而不是 SaaS 的最高控制器。

```text
LangGraph Node
     │
     ├── deterministic Python function
     │
     ├── Deep Agent execution
     │
     ├── Side Effect operation
     │
     └── Human interrupt
```

LangGraph checkpoint 只代表 Agent runtime state；业务 Project / Artifact / Billing 的真相仍在业务数据库。

---

# 9. Design Runtime Boundary

```text
Natural Language
      │
      ▼
Design Intent
      │
      ▼
Design IR
      │
      ▼
Constraint Validator
      │
      ▼
Canvas Compiler
      │
      ▼
Canvas Scene Graph
      │
      ▼
Renderer
```

## 9.1 Design IR 是 Domain Contract

禁止：

```text
Agent → Pixi Node
Agent → React component tree
Agent → raw canvas command
```

必须：

```text
Agent → Design Operation → Design IR → Compiler → Renderer
```

## 9.2 Source of Truth

- Project conceptual design state：Design IR / Artifact version。
- Runtime visual render state：Canvas Scene Graph。
- UI ephemeral state（selection/hover/panel）：Frontend State。

Canvas renderer 不是业务真相源。

---

# 10. Constraint Boundary

所有“不要动”要求必须机器化。

P0 约束：

```text
LOCK_POSITION
LOCK_SIZE
LOCK_CONTENT
LOCK_IDENTITY
LOCK_STYLE
LOCK_ASPECT_RATIO
LOCK_BRAND
LOCK_LAYER_ORDER
PROTECT_REGION
REQUIRE_CONTRAST
REQUIRE_SCANNABILITY
REQUIRE_BRAND_COMPLIANCE
```

任何 Design Operation：

```text
Proposed Mutation
       ↓
Constraint Engine
       ↓
 Allowed / Rejected / Needs Approval
```

Prompt 中重复用户约束可以作为提示，但不能取代 Constraint Engine。

---

# 11. Artifact / Version Boundary

Artifact 是所有可交付设计结果的统一抽象。

```text
Artifact
├── immutable identity
├── current version pointer
└── versions
     ├── parent version
     ├── source assets
     ├── model call
     ├── prompt/compiler version
     ├── design operations
     ├── agent run
     ├── quality score
     └── storage object
```

## 11.1 Version Principle

- 大修改、新生成：新 Version。
- 局部结构化修改：生成 Design Operation + 新 Version。
- 二进制不能原地覆盖。
- User-visible restore 创建新的 head，不破坏历史链。

## 11.2 Provenance

所有生成物必须至少能追踪：

```text
user instruction
project/task
agent run
model/provider
prompt compiler version
source assets
parent artifact/version
generation parameters
cost
quality results
```

---

# 12. Model Gateway Boundary

Agent 不知道供应商 SDK。

统一接口：

```text
ModelRequest
├── capability
├── modality
├── quality_target
├── latency_target
├── budget
├── language
├── dimensions
├── policy
└── payload
```

Gateway 流程：

```text
Request
  ↓
Capability Match
  ↓
Policy Filter
  ↓
Cost / Quality / Latency Ranking
  ↓
Provider Health
  ↓
Selected Model
  ↓
Adapter
  ↓
Normalized Response
```

P0 必须支持：

- Model Registry。
- Capability Registry。
- Routing policy。
- Fallback chain。
- Retry classification。
- usage/cost normalization。
- provider request id。
- model health state。

---

# 13. Tool / MCP Gateway Boundary

外部工具通过统一 Tool Descriptor：

```text
Tool
├── name
├── namespace
├── version
├── description
├── input_schema
├── output_schema
├── permission
├── side_effect_level
├── requires_approval
├── timeout
├── idempotency_policy
└── adapter
```

MCP 作为重要协议适配层，但 Domain 不依赖某个 MCP 版本实现。

MCP Adapter 必须处理：

- protocol version negotiation / compatibility adapter。
- tool discovery/cache。
- resource access。
- authentication / authorization metadata。
- tool call timeout。
- audit。
- output size limitation。
- prompt-injection boundaries。

2026-07-28 MCP 的 stateless core、header routing 和 cacheable list 设计可用于 remote MCP Gateway，但实现必须保留兼容层，不把协议细节泄漏到 Agent Domain。

---

# 14. Context / Memory / Knowledge Boundary

三者严格分离。

## Context

> 当前一次模型调用应该看到什么。

## Memory

> 用户、项目、品牌、Agent 需要跨会话记住什么。

## Knowledge

> 可以检索的事实/资料/文件集合。

流程：

```text
Task
 + Project
 + User instruction
 + Memory retrieval
 + Knowledge retrieval
 + Artifact state
 + Brand rules
 + Model capability
        ↓
Context Compiler
        ↓
Prompt Compiler
        ↓
Model Gateway
```

禁止把整段聊天历史无筛选塞给模型。

---

# 15. Data Topology

## 15.1 PostgreSQL Domains

```text
identity
organization
workspace
project
project_member
brand
brand_rule
asset
artifact
artifact_version
canvas_document
design_operation
constraint
task
task_dependency
recipe
agent_definition
agent_run
agent_run_step
memory
knowledge_document
model_usage
tool_usage
cost_ledger
quota
audit_event
outbox_event
job
approval
```

## 15.2 Redis

仅存可丢失或可重建数据：

- cache。
- rate limit state。
- ephemeral locks。
- queue coordination。
- websocket/SSE coordination。
- provider health cache。

不得把 Artifact、Billing、Project truth 只存在 Redis。

## 15.3 Object Storage

```text
/org/{org_id}/project/{project_id}/asset/...
/org/{org_id}/project/{project_id}/artifact/...
/org/{org_id}/project/{project_id}/export/...
/org/{org_id}/sandbox/{run_id}/...
```

对象默认 private，通过 signed URL 或受控代理访问。

---

# 16. Side Effect / Idempotency Boundary

外部有副作用的行为必须经过 Side Effect Gateway。

包括：

- 调用付费模型。
- 图片/视频生成。
- 扣额度。
- 支付。
- 外部写操作。
- 导出持久化。
- 第三方消息/发布。

统一 Operation Record：

```text
operation_id
idempotency_key
org_id
project_id
task_id
agent_run_id
operation_type
request_hash
provider
provider_request_id
status
attempt
estimated_cost
actual_cost
created_at
completed_at
```

规则：

1. 每个外部副作用先创建 operation。
2. 相同 idempotency key 已成功则返回历史结果。
3. Provider 超时不等于失败；优先查询 provider request status。
4. Retry 必须区分 safe retry 和 unknown outcome。
5. Billing 与 Artifact commit 使用 ledger/transaction/outbox 协调。

---

# 17. Security Trust Boundaries

```text
[Public Browser]
      │
      ▼
[Edge / Web]
      │  Trust Boundary A
      ▼
[API]
      │
      ├── AuthZ / Tenant Filter
      │
      │  Trust Boundary B
      ▼
[Agent Runtime]
      │
      ├── Model Gateway
      ├── Tool Gateway
      │
      │  Trust Boundary C
      ▼
[Sandbox / External Providers]
```

## 17.1 Mandatory P0 Security

- OIDC/session authentication abstraction。
- organization/workspace/project scoped authorization。
- RBAC。
- tenant_id/org_id enforced at repository/query layer。
- signed object URLs。
- Secret Manager abstraction。
- no provider secret in browser。
- Sandbox network policy。
- SSRF protection。
- uploaded-file validation。
- audit log。
- tool allowlist。
- risky tool HITL。
- prompt/tool injection defenses。
- cost/rate limit abuse protection。

## 17.2 Multi-Tenant Rule

所有 tenant-owned 数据必须具备明确 tenant scope。

禁止：

```text
SELECT * FROM artifacts WHERE id = ?
```

要求等价逻辑：

```text
WHERE organization_id = current_org
  AND id = artifact_id
```

数据库层与应用层至少双层保护。

---

# 18. Deployment Topology

## 18.1 Local Development

```text
Docker Compose
├── web
├── api
├── agent-runtime
├── worker-media
├── postgres
├── redis
├── object-storage emulator
└── mock-provider
```

## 18.2 Staging

```text
Container Platform
├── web xN
├── api xN
├── agent-runtime xN
├── media-worker xN
├── model-gateway xN
├── tool-gateway xN
└── sandbox workers

Managed / durable:
├── PostgreSQL
├── Redis
└── Object Storage
```

## 18.3 Production

逻辑拓扑与 staging 相同；根据实际负载选择容器编排环境。

生产必须允许：

- API 和 Agent worker 独立扩缩。
- media worker 独立扩缩。
- Provider Gateway 独立 circuit-break。
- PostgreSQL backup + PITR。
- Object Storage versioning/lifecycle。
- Redis 可替换，不作为唯一真相源。

LangSmith Agent Server 可作为 Agent deployment runtime 选项；若采用 standalone/self-hosted 模式，LUMI 业务数据库仍保持独立领域边界。

---

# 19. Observability Boundary

三类观察数据不能混为一谈。

## 19.1 AI Trace

LangSmith：

- Agent run。
- LLM spans。
- tool calls。
- prompt/model metadata。
- eval/feedback。

## 19.2 Application Telemetry

OpenTelemetry-compatible abstraction：

- API latency。
- errors。
- job latency。
- queue depth。
- DB latency。
- cache hit rate。

## 19.3 Business Metrics

业务数据库/analytics：

- projects created。
- generation success。
- user acceptance rate。
- repair rate。
- cost/project。
- margin。
- export completion。

LangSmith 不作为 Billing Ledger 或 Project Store。

---

# 20. Quality Boundary

质量系统分四层：

```text
Unit / Contract Tests
        ↓
Integration Tests
        ↓
AI Benchmark / LangSmith Eval
        ↓
Visual / Product Acceptance
```

任何 AI Prompt / Agent / Model / Skill 变更必须具备 benchmark profile。

生产 Release Gate 至少检查：

- planning success。
- constraint compliance。
- tool correctness。
- visual quality。
- identity consistency。
- cost regression。
- latency regression。
- recovery/idempotency。

---

# 21. Dependency Rules

允许依赖方向：

```text
UI
 ↓
Application / API
 ↓
Domain
 ↓
Ports / Interfaces
 ↓
Adapters / Infrastructure
```

Agent side：

```text
Agent Definitions
 ↓
Agent Runtime Interfaces
 ↓
Model/Tool Gateway Interfaces
 ↓
Provider Adapters
```

Design side：

```text
Design Intent
 ↓
Design IR
 ↓
Constraints
 ↓
Compiler
 ↓
Canvas Renderer
```

禁止反向：

- Domain importing provider SDK。
- Agent definition importing OpenAI/Gemini/etc. SDK。
- Design IR importing PixiJS objects。
- Billing depending on Redis-only state。
- Frontend owning canonical artifact version state。

---

# 22. Repository Boundary

冻结目标 Monorepo：

```text
LUMI-AI-DESIGN-OS/
│
├── apps/
│   ├── web/
│   ├── api/
│   ├── agent-runtime/
│   ├── worker-media/
│   └── admin/
│
├── packages/
│   ├── design-ir/
│   ├── design-constraints/
│   ├── event-schema/
│   ├── api-client/
│   ├── ui/
│   └── shared-types/
│
├── services/
│   ├── model-gateway/
│   ├── tool-gateway/
│   ├── sandbox-runtime/
│   ├── memory/
│   ├── knowledge/
│   ├── visual-critic/
│   └── asset-intelligence/
│
├── agents/
├── skills/
├── recipes/
├── evals/
├── db/
├── infra/
├── scripts/
├── docs/
└── .github/
```

NODE-02 可以先创建空目录占位与最小 runnable skeleton；不要求在 NODE-02 实现所有 service。

---

# 23. API Boundary

API 按 domain resource，而不是按页面设计。

首批 resource：

```text
/auth
/organizations
/workspaces
/projects
/brands
/assets
/artifacts
/canvas-documents
/tasks
/agent-runs
/approvals
/exports
/usage
/billing
```

Agent streaming：

```text
POST /agent-runs
GET  /agent-runs/{id}
GET  /agent-runs/{id}/stream
POST /agent-runs/{id}/resume
POST /agent-runs/{id}/cancel
```

API Contract 在 NODE-11 正式定义，本节点只冻结资源边界。

---

# 24. Realtime Boundary

SSE 作为 P0 Agent run/status streaming 的默认选择；双向高频协作通信在 P1 Collaboration 节点评估 WebSocket。

原因：

- Agent token/event stream 主要是 server → client。
- SSE 对重连、代理和 HTTP 基础设施更简单。
- Canvas 多人协作是独立问题，不强迫 Agent streaming 使用同一协议。

---

# 25. Human-in-the-Loop Boundary

HITL 是一等领域对象，不是聊天消息特殊情况。

Approval：

```text
approval_id
run_id
task_id
type
requested_action
risk_level
payload
status
requested_at
resolved_at
resolved_by
```

典型触发：

- 选择 Creative Direction。
- 批准 Logo。
- 高成本批量生成。
- 外部发布。
- 风险工具调用。
- 超预算继续执行。

LangGraph interrupt 用于 runtime suspend/resume；Approval 表用于业务事实和审计。

---

# 26. Cost Boundary

所有付费能力都要形成 Usage Event：

```text
usage_event
├── org
├── user
├── project
├── task
├── agent_run
├── provider
├── model/tool
├── quantity
├── provider_cost
├── customer_cost
└── currency
```

Cost Ledger 与 Provider 响应状态解耦。

Model Gateway 路由输入必须允许：

```text
max_cost
quality_target
latency_target
remaining_project_budget
remaining_user_quota
```

---

# 27. Failure Model

系统必须显式处理：

1. Provider 429。
2. Provider 5xx。
3. Provider timeout + unknown result。
4. Agent node crash。
5. Worker crash。
6. DB transaction rollback。
7. object upload partially completed。
8. Redis unavailable。
9. browser disconnect。
10. user cancels run。
11. run waiting approval for long period。
12. model removed/deprecated。
13. provider price/capability changed。

恢复原则：

```text
Checkpoint handles reasoning state.
Database handles business truth.
Idempotency handles side effects.
Outbox handles event delivery.
Artifact versioning handles design history.
```

---

# 28. Architecture Decision Records

以下 ADR 在 NODE-01 正式冻结。

## ADR-001 — LangGraph is the Control Plane

**Decision:** 所有长 Agent 生命周期由 LangGraph 控制；Deep Agents 作为自主执行层。  
**Reason:** 保留确定性状态、checkpoint、HITL、resume 与业务控制。  
**Rejected:** 整个平台只有一个自由 Deep Agent。

## ADR-002 — Deep Agents for Autonomous Work

**Decision:** 复杂探索、research、planning、subagent delegation 使用 Deep Agents。  
**Rejected:** 所有逻辑手写成大量固定 Graph nodes。

## ADR-003 — Design IR is Renderer-Independent

**Decision:** Design IR 独立于 React/Pixi/DOM renderer。  
**Rejected:** 直接保存前端 scene objects 作为领域模型。

## ADR-004 — Modular Monolith First

**Decision:** 业务核心模块化单体；Agent/Media/Gateway/Sandbox按资源与安全边界独立。  
**Rejected:** Day-1 大规模微服务。

## ADR-005 — PostgreSQL is Business Source of Truth

**Decision:** Project、Task、Artifact、Billing、Approval、Audit 落 PostgreSQL。  
**Rejected:** Redis 或 LangGraph checkpoint 替代业务数据库。

## ADR-006 — S3-compatible Object Storage for Binary Assets

**Decision:** 大型二进制对象只存 object storage。  
**Rejected:** bytea/base64 大量进入 PostgreSQL。

## ADR-007 — Gateway before Provider

**Decision:** Model 和 Tool provider 均必须走 Gateway abstraction。  
**Rejected:** Agent 代码直接依赖 provider SDK。

## ADR-008 — Side Effects are Idempotent

**Decision:** 所有付费/写外部系统操作进入统一 operation ledger。  
**Rejected:** LangGraph retry 直接重复第三方调用。

## ADR-009 — SSE for P0 Agent Streaming

**Decision:** Agent/status P0 使用 SSE；多人 Canvas 协作另行设计。  
**Rejected:** 所有实时能力强制 WebSocket。

## ADR-010 — CRDT does not own Design Domain

**Decision:** CRDT 是 P1 collaboration transport/state merge 技术，不是 Design IR 的语义模型。  
**Rejected:** 让 Yjs 数据结构成为唯一 design domain schema。

## ADR-011 — Benchmark before Provider Lock-in

**Decision:** 模型/Provider 必须通过 benchmark + cost + latency 决定路由。  
**Rejected:** 因开发方便硬编码单一模型。

## ADR-012 — Managed Deployment is Replaceable

**Decision:** 可以使用 LangSmith Agent Server/Deployment 加速生产，但保留独立业务 Domain 和 adapter，使部署形态可替换。  
**Rejected:** 产品核心数据模型绑定到单一托管部署平台。

## ADR-013 — MCP is an Adapter Boundary

**Decision:** MCP 是 Tool Gateway 的重要协议层，不是领域模型。  
**Rejected:** Agent Domain 到处直接保存 MCP session/protocol 对象。

## ADR-014 — Security is Tenant-First

**Decision:** 数据库、API、storage path 和 audit 从 P0 就携带 tenant scope。  
**Rejected:** MVP 单租户后期再补多租户。

## ADR-015 — Versioned Everything AI-facing

**Decision:** Agent / Skill / Recipe / Prompt Compiler / Model Policy / Design IR schema 都可版本化。  
**Rejected:** 隐式 Prompt 和配置散落源码。

---

# 29. P0 / P1 / P2 Freeze

## P0 — 可上线核心

- Auth / Organization / Workspace / Project。
- PostgreSQL / Redis / Object Storage。
- LangGraph Control Plane。
- Deep Agents Runtime。
- Agent/Skill/Recipe Registry basics。
- Task Graph。
- Model Gateway。
- Tool/MCP Gateway basics。
- Context / Memory basics。
- Sandbox Runtime。
- Design IR。
- Constraint Engine。
- Canvas Engine single-user。
- Artifact / Version / Provenance。
- Image generation/edit pipeline。
- Visual Critic V1。
- Cost Ledger / Quota。
- Audit / tenant isolation。
- LangSmith trace/eval。
- Benchmark Harness。
- Project / AI Workspace / Canvas / Asset / Export UI。

## P1 — 产品成熟

- Knowledge Engine advanced retrieval。
- Asset Intelligence。
- Brand Rules advanced engine。
- Identity consistency advanced engine。
- Video production pipeline。
- Collaboration / CRDT。
- approval workflows advanced UI。
- Provider health scoring。
- Experiment / feature flags。
- Admin / operations console。
- External integrations expansion。

## P2 — 平台化

- Public API / SDK。
- Public MCP Server。
- Marketplace / third-party Skills。
- organization governance advanced。
- automatic prompt/policy optimization。
- data flywheel automation。
- large-enterprise deployment profiles。

---

# 30. Architecture Invariants

后续代码必须持续满足：

1. **No direct provider access from UI.**
2. **No direct provider SDK from domain/agent definitions.**
3. **No host shell for Agent.**
4. **No business truth only in Redis/checkpoint.**
5. **No mutable overwrite of delivered artifact binary.**
6. **No paid side effect without idempotency record.**
7. **No tenant-owned object without tenant scope.**
8. **No Canvas renderer object as canonical Design IR.**
9. **No production Agent/Skill/Recipe without version.**
10. **No AI behavior release without benchmark.**
11. **No privileged tool call without policy evaluation.**
12. **No global context dump without Context Compiler.**

这些 invariants 后续应逐步转化为 lint、contract test、architecture test 和 CI checks。

---

# 31. NODE-01 Acceptance Criteria

本节点完成必须满足：

- [x] Product boundary frozen。
- [x] Architecture style frozen。
- [x] Core technology responsibilities frozen。
- [x] Runtime topology defined。
- [x] Agent topology defined。
- [x] Design runtime boundary defined。
- [x] Data topology defined。
- [x] Trust/security boundaries defined。
- [x] Deployment topology defined。
- [x] Side effect/idempotency policy defined。
- [x] Observability boundary defined。
- [x] Repository target topology defined。
- [x] P0/P1/P2 frozen。
- [x] ADR set created。
- [x] Architecture invariants documented。

**Result:** PASS

---

# 32. Next Node

```text
NODE-02 — Repository Bootstrap
```

NODE-02 交付：

- Monorepo directory skeleton。
- Python workspace/bootstrap。
- TypeScript workspace/bootstrap。
- Web runnable shell。
- API health endpoint。
- Agent runtime health endpoint。
- Worker bootstrap。
- shared config。
- `.env.example`。
- code quality baseline。
- test baseline。
- local development commands。
- root README。

NODE-02 完成定义：

```text
clone repo
  ↓
install
  ↓
start local stack
  ↓
web / api / agent / worker all healthy
  ↓
tests pass
```

---

# 33. Authoritative References Reviewed for NODE-01

本节点架构冻结参考了以下一手资料，并仅把这些产品能力当作基础设施事实，不把外部框架的数据模型直接当作 LUMI Domain Model：

- LangGraph Persistence / checkpoint / fault-tolerance：`https://docs.langchain.com/oss/python/langgraph/persistence`
- Deep Agents Overview：`https://docs.langchain.com/oss/python/deepagents/overview`
- Deep Agents Skills / Subagents：`https://docs.langchain.com/oss/python/deepagents/skills`
- LangSmith Agent Server runtime architecture：`https://docs.langchain.com/langsmith/agent-server`
- LangSmith Deployment：`https://docs.langchain.com/langsmith/deployment`
- Model Context Protocol Architecture：`https://modelcontextprotocol.io/docs/learn/architecture`
- MCP 2026-07-28 specification release：`https://blog.modelcontextprotocol.io/posts/2026-07-28/`

---

# 34. Freeze Statement

> **Architecture V2 is FROZEN at NODE-01.**

从 NODE-02 开始，任何改变以下内容的提议都必须新增 ADR：

- Control Plane owner。
- Design IR boundary。
- canonical data ownership。
- Provider Gateway boundary。
- Sandbox security boundary。
- tenant model。
- Artifact version semantics。
- side-effect semantics。
- primary persistence strategy。

**NODE-01 — COMPLETE.**
