# LUMI AI Design OS — Master Implementation Plan

> 文档状态：BASELINE / NODE-00 COMPLETE  
> 架构基线：LUMI AI Design OS — Architecture V2 Baseline  
> 目标：从零搭建一个可真实部署、可持续迭代、面向生产环境的 AI Design Agent 产品级系统，功能基准参考 Lovart.ai，但不复制其专有代码、商标、视觉资产或受保护实现。  
> 仓库：`zhangjaky71-stack/LUMI-AI-DESIGN-OS`  
> 原则：文档驱动开发；每个节点完成即提交 GitHub；任何实现必须有测试和验收标准。

---

## 0. 项目协作约定

本项目默认用户是非工程背景，因此执行策略如下：

1. 不要求用户事先准备架构资料、技术文档或开发脚手架。
2. 所需公开技术资料、SDK 文档、接口说明由实施方自行检索并优先采用官方/一手资料。
3. 能自动生成的配置、代码、测试、Mock 数据、迁移脚本、Docker 文件、CI 配置全部自动生成。
4. 只有无法代替用户完成的外部动作才需要用户参与，例如：付费云账号开通、商业 API Key、域名购买、企业实名认证、支付商户签约等。
5. 所有 Secret 仅通过环境变量或 Secret Manager 注入，不进入 Git。
6. 每个开发节点必须同时交付：设计文档、代码、测试、验收记录、必要的迁移/回滚说明。
7. 每完成一个节点立即上传本仓库，不把聊天记录作为唯一项目知识源。

---

# 1. 产品目标

LUMI 的目标不是“会调用生图 API 的聊天机器人”，而是一个 AI Design Operating System。

最终用户应该能够：

```text
一句自然语言需求
        ↓
自动理解项目与设计目标
        ↓
生成结构化 Brief
        ↓
研究市场 / 品牌 / 参考方向
        ↓
自主规划完整设计任务
        ↓
调用不同专业 Agent 与不同 AI 模型
        ↓
生成可编辑设计成果
        ↓
在无限 Canvas 中继续创作
        ↓
局部修改而不是整图重做
        ↓
保持产品 / Logo / 人物 / 品牌一致性
        ↓
自动 Visual QA + Repair
        ↓
生成多渠道、多尺寸、多格式衍生资产
        ↓
版本管理 / 协作 / 审批 / 导出
```

系统最终必须同时具备：

- Agent 自主性
- 确定性工作流控制
- 多模型路由
- 多 Agent 协同
- Infinite Canvas
- Design IR
- 局部编辑
- Brand Kit
- Asset 管理
- 图片/视频生成与处理
- Visual Critic
- 长任务恢复
- 人机协作
- 多租户
- 计费与成本控制
- 可观测性
- Benchmark / Regression
- Production Deployment

---

# 2. 竞品功能基准

公开产品能力基准重点关注：

1. Prompt / Reference / Brand Kit 输入。
2. Agent 自动研究、规划、生成、修改和交付。
3. 自动选择不同图片/视频/语言模型。
4. Infinite Canvas 统一组织生成结果与编辑结果。
5. Touch Edit / Element Edit，局部修改指定元素。
6. Brand Kit 自动约束颜色、字体、Logo、视觉风格。
7. 批量生成 Variants。
8. 同一设计自动适配不同尺寸和渠道。
9. 输出图片、矢量、PDF、分层或可编辑设计文件。
10. 完整项目包而非单张图片。

LUMI 的验收采用“能力等价/更强”原则，而不是 UI 像素级复制。

---

# 3. 最终验收标准

## 3.1 Agent 验收

必须能够：

- 理解模糊设计需求。
- 主动补全 Brief。
- 自动拆分 10+ 步长任务。
- 自动选择 Agent / Skill / Tool / Model。
- 支持至少 Research、Strategy、Creative、Image、Layout、Copy、Video、Critic、Export 等专业能力。
- 长任务可以暂停、恢复、失败重试。
- 关键阶段支持 Human Approval。
- Agent 执行路径、成本、Tool Call、模型调用可追踪。

## 3.2 设计系统验收

必须具备：

- Infinite Canvas。
- Frame / Group / Text / Image / Vector / Shape / Mask / Video。
- Layer Tree。
- Zoom / Pan / Select / Multi-select。
- Move / Resize / Rotate / Align / Distribute。
- Undo / Redo。
- Version / Fork / Restore。
- Auto Layout 或基础 Constraint Layout。
- Design IR 与 Canvas 双向映射。
- 元素锁定与保护区域。
- 局部编辑。

## 3.3 AI 生成验收

至少覆盖：

- 文生图。
- 图生图。
- Reference Image。
- Inpainting / Mask Edit。
- Background Replace。
- Remove Background。
- Upscale。
- Product Scene。
- Brand Poster。
- Logo / Vector 辅助生成流程。
- 多尺寸衍生。
- 图生视频 / 文生视频适配器。
- 自动模型选择与 fallback。

## 3.4 Brand 验收

Brand Kit 至少包括：

- Logo variants。
- Color palette。
- Typography。
- Brand voice。
- Photography style。
- Illustration style。
- Layout rules。
- Allowed / Forbidden rules。
- Reference assets。

生成资产必须可执行 Brand Consistency 检查。

## 3.5 SaaS 验收

必须具备：

- Auth。
- Organization / Workspace。
- Project。
- RBAC。
- Multi-tenancy。
- Usage Metering。
- Quota。
- Cost Ledger。
- Subscription abstraction。
- Admin Console。
- Audit Log。
- Object Storage。
- Rate Limit。
- Error / Incident tracing。

## 3.6 Production 验收

必须做到：

- Docker 化。
- Development / Staging / Production 环境隔离。
- CI/CD。
- Database migration。
- Backup / Restore。
- Secrets management。
- Health check。
- Metrics / Logs / Traces。
- P95 latency 与成功率指标。
- 自动测试。
- Benchmark release gate。
- Rollback。

---

# 4. Architecture V2 总体结构

```text
                         LUMI AI DESIGN OS
                                │
┌───────────────────────────────┴───────────────────────────────┐
│                     EXPERIENCE PLANE                          │
│ Chat │ Canvas │ Project │ Assets │ Timeline │ Review │ Admin │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                    AGENT CONTROL PLANE                        │
│                         LangGraph                             │
│ Workflow / State / Checkpoint / Interrupt / Resume / Retry   │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                AUTONOMOUS INTELLIGENCE                       │
│ Deep Agents + LangChain                                      │
│ Planning / Subagents / Skills / Tools / Structured Output    │
└───────────────────────────────┬───────────────────────────────┘
                                │
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
       Recipe Engine       Agent Registry      Skill Registry
             │
             ▼
          Task Graph
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                 CONTEXT INTELLIGENCE                         │
│ Context │ Memory │ Knowledge │ RAG │ Prompt Compiler         │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                    AI INFRASTRUCTURE                          │
│ Model Gateway │ Capability Registry │ Tool/MCP Gateway       │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                    EXECUTION RUNTIME                         │
│ Sandbox │ Queue │ Event Bus │ Workers │ Idempotency          │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                   DESIGN INTELLIGENCE                        │
│ Design IR │ Constraint Engine │ Brand Rules                 │
│ Canvas Engine │ Artifact Engine │ Media Pipeline             │
│ Identity Engine │ Visual Critic                              │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                        DATA PLANE                             │
│ PostgreSQL │ Redis │ Vector │ Object Storage │ Event Store   │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                     PLATFORM PLANE                           │
│ Security │ Tenant │ Billing │ Quota │ Cost │ Licensing       │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                  QUALITY / OPERATIONS                        │
│ LangSmith │ Benchmark │ Eval │ SRE │ Admin │ Data Flywheel   │
└───────────────────────────────────────────────────────────────┘
```

---

# 5. 核心架构职责

## LangGraph

负责确定性、生命周期和状态：

- Workflow。
- Graph State。
- Checkpoint。
- Interrupt / Resume。
- Human Approval。
- Retry。
- Recovery。
- Branching。

## Deep Agents

负责自主性：

- Planning。
- Todo。
- Context offload。
- Filesystem。
- Subagents。
- Skills。
- 长任务自主执行。

## LangChain

负责基础 Agent 能力：

- Model abstraction。
- Tools。
- Middleware。
- Structured output。
- RAG。
- Provider integration。

## LangSmith

负责 AI 质量与可观测性：

- Tracing。
- Evaluation。
- Dataset。
- Experiment。
- Online monitoring。
- Agent trajectory analysis。

## Design IR

Agent 与设计系统之间唯一稳定的中间语言。

Agent 不直接操作前端 Canvas 内部实现。

## Constraint Engine

负责机器可执行的“不能改”和“必须满足”。

## Canvas Engine

负责交互式编辑和渲染。

## Artifact Engine

负责生成成果、版本、血缘、派生关系和导出。

---

# 6. 默认技术栈

> 具体版本在开发节点执行时以当时最新兼容稳定版锁定，并写入 lockfile；不在架构文档硬编码易过时的小版本。

## Frontend

- TypeScript。
- React。
- Next.js。
- Tailwind CSS。
- Design System：自建 tokens + accessible components。
- Canvas：抽象 `CanvasAdapter`，通过专项 benchmark 决定 PixiJS / Konva / Fabric 或混合渲染方案。
- State：server-state 与 editor-state 分离。
- Streaming：SSE 为默认，必要场景 WebSocket。

## Backend / Agent

- Python。
- FastAPI 作为产品 API/BFF 层之一。
- LangGraph。
- Deep Agents。
- LangChain。
- Pydantic schema-first。
- LangSmith tracing/eval。

## Data

- PostgreSQL：主事务数据库。
- Redis：cache / rate limit / ephemeral locks / realtime support。
- pgvector 或独立 Vector Store：Memory / Knowledge / Asset semantic retrieval。
- S3-compatible Object Storage：图片、视频、文件、导出结果。

## Runtime

- Docker。
- Docker Compose：本地开发。
- Kubernetes 或托管容器平台：生产规模化阶段。
- Agent Sandbox：隔离 Python / Node / FFmpeg / ImageMagick / Browser。

## CI/CD

- GitHub Actions。
- Lint / Typecheck / Unit Test / Integration Test / Eval Gate / Build / Migration Check。

---

# 7. Monorepo 目标结构

```text
LUMI-AI-DESIGN-OS/
│
├─ apps/
│  ├─ web/
│  ├─ api/
│  ├─ agent-runtime/
│  ├─ worker-media/
│  └─ admin/
│
├─ packages/
│  ├─ design-ir/
│  ├─ design-constraints/
│  ├─ canvas-sdk/
│  ├─ artifact-sdk/
│  ├─ api-client/
│  ├─ event-schema/
│  ├─ ui/
│  └─ shared-types/
│
├─ services/
│  ├─ model-gateway/
│  ├─ tool-gateway/
│  ├─ memory/
│  ├─ knowledge/
│  ├─ asset-intelligence/
│  ├─ visual-critic/
│  └─ billing/
│
├─ agents/
│  ├─ director/
│  ├─ brief/
│  ├─ research/
│  ├─ strategy/
│  ├─ creative-director/
│  ├─ image/
│  ├─ layout/
│  ├─ copy/
│  ├─ video/
│  ├─ critic/
│  └─ export/
│
├─ skills/
│  ├─ poster-design/
│  ├─ logo-design/
│  ├─ brand-strategy/
│  ├─ moodboard/
│  ├─ typography/
│  ├─ product-render/
│  ├─ image-edit/
│  └─ video-design/
│
├─ recipes/
│  ├─ brand-identity/
│  ├─ campaign/
│  ├─ social-kit/
│  ├─ poster/
│  └─ product-launch/
│
├─ db/
│  ├─ migrations/
│  ├─ seeds/
│  └─ schema/
│
├─ evals/
│  ├─ datasets/
│  ├─ evaluators/
│  ├─ benchmarks/
│  └─ reports/
│
├─ infra/
│  ├─ docker/
│  ├─ compose/
│  ├─ kubernetes/
│  ├─ terraform/
│  └─ monitoring/
│
├─ docs/
│  ├─ architecture/
│  ├─ specs/
│  ├─ api/
│  ├─ adr/
│  ├─ runbooks/
│  └─ acceptance/
│
└─ .github/
   └─ workflows/
```

---

# 8. Agent Team

```text
LUMI Director Agent
│
├─ Brief Agent
├─ Planner Agent
├─ Research Agent
├─ Brand Strategy Agent
├─ Creative Director Agent
├─ Moodboard Agent
├─ Copywriting Agent
├─ Typography Agent
├─ Layout Agent
├─ Image Agent
├─ Image Edit Agent
├─ Product Render Agent
├─ Video Agent
├─ Motion Agent
├─ Critic Agent
├─ Brand Consistency Agent
├─ Identity Agent
└─ Export Agent
```

原则：

- Director 负责委派，不包办所有任务。
- 高输出量 Tool 任务优先交给 Subagent，隔离上下文。
- 每个 Agent 有独立 Prompt、Model Policy、Tool Policy、Skill、Memory Policy、Budget 和 Eval Profile。
- Agent 定义全部版本化。

---

# 9. Workflow / Recipe

不采用“每次都让 LLM 从零规划”的方式。

采用：

```text
Recipe Skeleton
+
Dynamic Agent Planning
```

例如 Brand Identity：

```text
Intake
 ↓
Brief
 ↓
Research
 ↓
Strategy
 ↓
Moodboard
 ↓
Approval
 ↓
Logo Directions
 ↓
Critic
 ↓
Refinement
 ↓
Typography
 ↓
Color System
 ↓
Brand Kit
 ↓
Applications
 ↓
Export
```

Recipe 负责确定性骨架；Deep Agent 负责骨架内部自主执行。

---

# 10. Design IR V1

至少定义：

```text
Document
Frame
Group
Text
Image
Vector
Shape
Video
Mask
Effect
Component
Instance
Guide
Grid
```

所有节点至少具有：

```text
id
type
role
parent
children
position
size
rotation
style
semantic_role
asset_binding
brand_binding
constraints
metadata
version
```

支持 operation：

```text
CREATE
UPDATE
DELETE
MOVE
RESIZE
ROTATE
REPLACE
LOCK
UNLOCK
GROUP
UNGROUP
REORDER
APPLY_STYLE
BIND_ASSET
```

---

# 11. Constraint Engine

首版约束：

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

任何 Agent Edit Plan 必须先通过 Constraint Validator。

---

# 12. Model Gateway

Agent 禁止直接依赖厂商 SDK。

```text
Agent
 ↓
Model Gateway
 ↓
Capability Match
 ↓
Policy / Cost / Health Router
 ↓
Provider Adapter
 ↓
Model Provider
```

Gateway 必须具有：

- Model Registry。
- Capability Registry。
- Provider Adapter。
- Router。
- Fallback Chain。
- Retry Policy。
- Rate Limit。
- Cost Estimate。
- Usage Metering。
- Health Score。
- Response Normalization。

Provider 适配分组：

- LLM。
- Image generation。
- Image editing。
- Embedding。
- OCR / Vision。
- Video generation。
- Audio。
- Search / Research。

具体 Provider 与模型名单由独立 `Model-Provider-Matrix` 节点持续更新，避免架构绑定单一厂商。

---

# 13. Tool / MCP Gateway

工具统一经过 Gateway：

```text
Agent
 ↓
Tool Gateway
 ↓
Auth / Policy / Audit / Rate Limit
 ↓
MCP or Native Adapter
 ↓
External System
```

首批 Tool Domain：

- Web Search。
- Browser。
- File。
- Object Storage。
- Image processing。
- Video processing。
- Database read tools。
- Design tools。
- Export tools。
- GitHub / source-control integration。

MCP 作为标准扩展协议优先，但保留 Native Adapter 处理性能、安全或供应商专用能力。

---

# 14. Context / Memory / Knowledge

三者必须分开。

## Context

当前一次 Agent Run 真正需要看到的信息。

## Memory

跨会话保留的用户、项目、品牌、Agent 经验。

## Knowledge

可检索的文档、规范、素材、品牌资料、历史设计和公开研究内容。

Context Compiler：

```text
User Instruction
+
Task State
+
Project Context
+
Relevant Memory
+
Retrieved Knowledge
+
Brand Rules
+
Artifact State
+
Model Capability
        ↓
Context Compiler
        ↓
Prompt Compiler
```

禁止把整个聊天历史无差别塞入模型。

---

# 15. Artifact / Version / Provenance

每个 Artifact 必须保存：

```text
artifact_id
project_id
task_id
agent_run_id
type
version
parent_artifact_id
source_assets
model
prompt_hash
generation_parameters
storage_uri
quality_score
created_at
```

目标：

- Undo / Redo。
- Restore。
- Fork。
- Branch。
- Compare。
- Partial regeneration。
- Provenance trace。

---

# 16. Media Pipeline

## Image Pipeline

```text
Generate
 ↓
Decode / Validate
 ↓
Crop / Resize
 ↓
Mask / Local Edit
 ↓
Remove BG
 ↓
Relight / Color
 ↓
Upscale
 ↓
Typography / Composite
 ↓
Visual QA
 ↓
Artifact
```

## Video Pipeline

```text
Brief
 ↓
Script
 ↓
Storyboard
 ↓
Shot List
 ↓
Keyframes
 ↓
Generate Clips
 ↓
Edit
 ↓
Audio / Subtitle
 ↓
Render
 ↓
QA
 ↓
Artifact
```

耗时媒体任务进入 Queue/Worker，不阻塞 Web 请求。

---

# 17. Visual Critic

至少评估：

- Composition。
- Hierarchy。
- Typography。
- Alignment。
- Contrast。
- Brand consistency。
- Product identity。
- Logo integrity。
- Text accuracy。
- QR readability。
- Visual defects。
- Resolution。

失败后生成结构化 Repair Plan，而不是只输出一段评论。

---

# 18. 前端产品功能

## 核心页面

1. Landing / Pricing。
2. Login / Signup。
3. Workspace Home。
4. Project List。
5. New Project / Brief。
6. Main AI Design Workspace。
7. Infinite Canvas。
8. Chat / Agent Timeline。
9. Asset Library。
10. Brand Kit。
11. Version History。
12. Export Center。
13. Team / Collaboration。
14. Usage / Billing。
15. Settings。
16. Admin Console。

## Workspace 布局

建议：

```text
┌──────────────────────────────────────────────┐
│ Top Toolbar                                  │
├──────────┬───────────────────────┬───────────┤
│ Project  │                       │ Inspector │
│ Assets   │    Infinite Canvas    │ Layers    │
│ Brand    │                       │ Properties│
│          │                       │           │
├──────────┴───────────────────────┴───────────┤
│ Chat / Agent Timeline / Job Progress         │
└──────────────────────────────────────────────┘
```

---

# 19. 后端服务边界

首期采用模块化单体 + 独立 Agent/Media Worker，避免过早微服务化。

```text
API Application
├─ auth
├─ organizations
├─ projects
├─ brands
├─ assets
├─ canvas
├─ artifacts
├─ agents
├─ workflows
├─ models
├─ tools
├─ usage
├─ billing
└─ admin

Agent Runtime
├─ graph
├─ deep_agents
├─ agents
├─ skills
├─ recipes
├─ memory
└─ context

Media Worker
├─ image
├─ video
├─ render
└─ export
```

只有出现明确扩容、隔离或部署需求时再拆独立服务。

---

# 20. 数据领域

数据库 Domain 至少包括：

```text
Identity
Organization
Workspace
Membership
Project
Conversation
Message
AgentRun
Task
TaskDependency
WorkflowRun
Approval
Brand
BrandRule
Asset
Artifact
ArtifactVersion
CanvasDocument
CanvasNode
Constraint
ModelProvider
ModelDefinition
ModelCapability
ToolDefinition
ToolCall
Job
UsageEvent
CostLedger
Subscription
Quota
AuditLog
Memory
KnowledgeDocument
EmbeddingRecord
Evaluation
BenchmarkRun
FeatureFlag
```

完整字段、索引、外键、RLS/tenant 设计进入 Database Schema 节点。

---

# 21. Security Baseline

必须从第一阶段进入设计：

- Authentication。
- Authorization。
- RBAC。
- Tenant Isolation。
- Secret Manager。
- Tool Permission。
- Sandbox Isolation。
- SSRF 防护。
- File type / size validation。
- Malware/unsafe file extension policy。
- Prompt Injection 防护。
- Rate Limit。
- Audit Log。
- Signed URL。
- Least privilege。
- Data retention policy。

任何能产生外部副作用的 Tool 必须经过 Policy + Audit。

---

# 22. Side Effect / Idempotency

对以下操作要求 idempotency key：

- 图片生成。
- 视频生成。
- 扣积分/扣余额。
- 文件导出。
- 第三方写 API。
- Artifact 创建。
- 支付操作。

避免 LangGraph retry/resume 导致重复调用和重复计费。

---

# 23. Cost / Billing

计费必须能追踪到：

```text
Organization
User
Project
Task
AgentRun
ModelCall
ToolCall
Job
Artifact
```

记录：

```text
estimated_cost
reserved_cost
actual_cost
provider_cost
customer_charge
remaining_budget
```

Model Router 可以根据预算自动降级或减少 variants。

---

# 24. Observability

三层：

## AI

LangSmith：trace / trajectory / eval / prompt experiment。

## Application

- Request logs。
- Error tracing。
- API metrics。
- DB metrics。
- Queue metrics。

## Business

- Activation。
- Project completion。
- Asset generation success。
- User selection rate。
- Edit rate。
- Export rate。
- Cost per successful project。

---

# 25. Benchmark Harness

至少包含：

```text
Brief understanding
Planning
Tool selection
Research
Structured output
Design generation
Image editing
Constraint following
Identity consistency
Brand consistency
Typography
Visual quality
Long task recovery
Human approval
Cost
Latency
Provider failover
```

每个关键组件至少准备：

- Golden cases。
- Negative cases。
- Edge cases。
- Regression cases。

新版本必须通过 Offline Eval 再进入 Staging。

---

# 26. 环境策略

```text
local
 ↓
dev
 ↓
staging
 ↓
production
```

不同环境：

- 独立 DB。
- 独立 Bucket prefix 或 Bucket。
- 独立 API keys。
- 独立 OAuth callback。
- 独立 tracing project。

禁止开发环境直接访问生产 Secret。

---

# 27. CI/CD

Pull Request 必须执行：

```text
format
lint
typecheck
unit test
schema validation
migration check
security scan
integration test
agent eval smoke
build
```

合并到 main 后：

```text
build artifact
 ↓
deploy staging
 ↓
smoke test
 ↓
benchmark gate
 ↓
manual/automatic production promotion
```

---

# 28. 测试策略

## Unit

业务函数、IR transform、constraint validator、router policy。

## Integration

Database、Storage、Model adapter、Tool adapter、Graph checkpoint。

## Contract

API schema、event schema、provider normalization。

## E2E

Browser 完整用户路径。

## AI Eval

非确定性 Agent/Model 质量。

## Chaos / Recovery

Provider failure、worker crash、network timeout、resume、duplicate request。

---

# 29. GitHub 节点交付规则

每个节点：

```text
NODE-XX
│
├─ docs
├─ source code
├─ tests
├─ migration/config（如需要）
├─ acceptance evidence
└─ commit
```

Commit 建议：

```text
feat(node-12): implement model gateway routing

docs(node-05): define design IR v1

test(node-24): add visual critic benchmark
```

任何 Node 只有在下面条件同时满足才算 COMPLETE：

- 文档完成。
- 实现完成或节点明确为纯设计节点。
- 测试通过。
- 验收条件通过。
- 已上传 GitHub。

---

# 30. 实施阶段与节点

## Phase -1 — Repository & Engineering Foundation

### NODE-00 Master Implementation Plan
本文件。

### NODE-01 Architecture V2 Freeze
输出正式系统架构、ADR、边界、依赖图。

### NODE-02 Repository Bootstrap
Monorepo、Python/Node 工具链、lint、format、test、env example。

### NODE-03 Local Infrastructure
Docker Compose：Postgres、Redis、Object Storage 等。

### NODE-04 CI Foundation
GitHub Actions 基础流水线。

---

## Phase 0 — Benchmark Before Build

### NODE-05 Benchmark Harness V2
建立 eval framework。

### NODE-06 Lovart Capability Acceptance Matrix
把产品目标转换为可测功能矩阵。

### NODE-07 Model Provider Matrix
联网核验当前可用模型、API、价格/能力/限制，并形成 adapter roadmap。

### NODE-08 Canvas Technology Spike
对候选 Canvas runtime 做性能与功能 POC。

---

## Phase 1 — Domain & Contract Foundation

### NODE-09 Domain Model

### NODE-10 Database Schema

### NODE-11 API Contract

### NODE-12 Event Protocol

### NODE-13 Design IR Specification

### NODE-14 Constraint Engine Specification

### NODE-15 Artifact / Version / Provenance Specification

---

## Phase 2 — Core Platform Runtime

### NODE-16 Auth / Tenant / RBAC

### NODE-17 Project / Workspace Core

### NODE-18 Asset Storage

### NODE-19 Job Queue / Event Bus

### NODE-20 Side Effect / Idempotency

### NODE-21 Sandbox Runtime

---

## Phase 3 — AI Infrastructure

### NODE-22 Model Gateway

### NODE-23 Capability Registry

### NODE-24 Provider Health / Fallback

### NODE-25 Tool Gateway

### NODE-26 MCP Integration

### NODE-27 Usage / Cost Ledger

---

## Phase 4 — Agent Intelligence

### NODE-28 LangGraph Control Plane

### NODE-29 Deep Agents Runtime

### NODE-30 Agent Registry

### NODE-31 Skill Registry

### NODE-32 Recipe Engine

### NODE-33 Task Graph / Planning Ledger

### NODE-34 Context Engine

### NODE-35 Memory Engine

### NODE-36 Knowledge / Retrieval

### NODE-37 Director + Core Subagents

---

## Phase 5 — Design Intelligence

### NODE-38 Design IR Runtime

### NODE-39 Constraint Validator

### NODE-40 Canvas Engine

### NODE-41 Canvas Compiler

### NODE-42 Artifact Engine

### NODE-43 Brand Kit / Rules Engine

### NODE-44 Identity Engine

### NODE-45 Asset Intelligence

---

## Phase 6 — Generation & Quality

### NODE-46 Image Generation Pipeline

### NODE-47 Image Edit Pipeline

### NODE-48 Video Pipeline

### NODE-49 Export Pipeline

### NODE-50 Visual Critic

### NODE-51 Auto Repair Loop

---

## Phase 7 — Product Frontend

### NODE-52 App Shell / Design System

### NODE-53 Project Home

### NODE-54 AI Workspace Chat

### NODE-55 Infinite Canvas UI

### NODE-56 Inspector / Layers / Asset Panel

### NODE-57 Agent Timeline / Progress

### NODE-58 Brand Kit UI

### NODE-59 Versions / History

### NODE-60 Export Center

---

## Phase 8 — SaaS / Collaboration

### NODE-61 Team Collaboration

### NODE-62 Approval / Review

### NODE-63 Billing / Quota

### NODE-64 Admin Console

### NODE-65 Audit / Moderation

---

## Phase 9 — Production Hardening

### NODE-66 Security Hardening

### NODE-67 Observability / LangSmith

### NODE-68 SRE / Backup / Recovery

### NODE-69 Load / Performance Testing

### NODE-70 AI Regression Gate

### NODE-71 Staging Acceptance

### NODE-72 Production Deployment

### NODE-73 Final Product Acceptance

---

# 31. 核心端到端验收场景

## Scenario A — 新品牌完整项目

用户输入：

> 给我创建一个高端精品咖啡品牌，包括品牌定位、Logo、字体、颜色、包装、菜单、海报、社交媒体素材和品牌手册。

必须完成：

- Brief。
- Research。
- Strategy。
- Moodboard。
- Approval。
- Design generation。
- Brand Kit。
- Cross-format assets。
- QA。
- Export package。

## Scenario B — 局部修改

用户：

> 产品和 Logo 都不要动，把背景改为黑色，把标题缩小 15%。

必须：

- Design IR 定位节点。
- Lock product / logo。
- 只更新 background / headline。
- Constraint 验证通过。
- 新建 Artifact Version。

## Scenario C — 多尺寸适配

用户：

> 基于当前海报输出 1:1、4:5、9:16 三套。

必须：

- 不是简单拉伸。
- 自动 layout adaptation。
- 保持品牌与主体。
- 每个尺寸独立 QA。

## Scenario D — Provider 故障

Primary image model 不可用时：

- Health 识别失败。
- Router 选择 fallback。
- Task 不丢失。
- 成本记录正确。
- UI 显示恢复状态。

## Scenario E — 中断恢复

Agent 在长任务中 worker crash：

- 从 checkpoint 恢复。
- 已成功副作用不重复。
- 不重复扣费。
- 继续后续 Task。

---

# 32. 用户参与最小化方案

默认由实施方处理：

- 技术选型。
- 官方文档检索。
- 数据库设计。
- Prompt / Agent definition。
- Schema。
- API contract。
- Docker。
- 测试。
- Seed data。
- Benchmark dataset 初版。
- GitHub 提交。
- CI 配置。

只在以下不可替代事项需要用户动作：

1. 购买或绑定付费 API 服务。
2. 提供生产 API Key。
3. 支付平台/域名/云厂商实名和账单授权。
4. 最终产品商业策略或法律条款确认。

即使这些暂时没有，也必须先提供 Mock/Adapter，使工程可以继续开发。

---

# 33. 开发原则

1. Schema-first。
2. Contract-first。
3. Test-first for critical runtime。
4. Eval-first for AI behavior。
5. Provider-independent。
6. No secrets in source。
7. Deterministic core + autonomous edges。
8. Async for expensive media jobs。
9. Structured state over free-form text。
10. Version everything：Agent / Skill / Recipe / Prompt / Model policy / IR / API。
11. Observability from day one。
12. Cost is a first-class metric。
13. Security is not a final-phase patch。
14. Every user-visible AI result becomes an Artifact。
15. Every Artifact has provenance。

---

# 34. Architecture Freeze 后的文档序列

后续将逐一形成实施级文档：

```text
01-ARCHITECTURE-V2-FROZEN.md
02-REPOSITORY-BOOTSTRAP.md
03-LOCAL-INFRASTRUCTURE.md
04-CI-FOUNDATION.md
05-BENCHMARK-HARNESS-V2.md
06-PRODUCT-ACCEPTANCE-MATRIX.md
07-MODEL-PROVIDER-MATRIX.md
08-CANVAS-TECH-SPIKE.md
09-DOMAIN-MODEL-V2.md
10-DATABASE-SCHEMA-V2.md
11-API-CONTRACT-V2.md
12-EVENT-PROTOCOL-V1.md
13-DESIGN-IR-SPEC-V1.md
14-CONSTRAINT-ENGINE-SPEC-V1.md
15-ARTIFACT-VERSION-PROVENANCE-V1.md
16-SECURITY-MULTITENANCY-V1.md
17-ASSET-STORAGE-V1.md
18-JOB-EVENT-RUNTIME-V1.md
19-IDEMPOTENCY-V1.md
20-SANDBOX-RUNTIME-V1.md
21-MODEL-GATEWAY-V1.md
22-CAPABILITY-REGISTRY-V1.md
23-PROVIDER-HEALTH-V1.md
24-TOOL-MCP-GATEWAY-V1.md
25-COST-USAGE-V1.md
26-LANGGRAPH-CONTROL-PLANE-V2.md
27-DEEP-AGENTS-RUNTIME-V1.md
28-AGENT-REGISTRY-V1.md
29-SKILL-SYSTEM-V1.md
30-RECIPE-ENGINE-V1.md
31-TASK-GRAPH-V1.md
32-CONTEXT-MEMORY-KNOWLEDGE-V1.md
33-AGENT-TEAM-V1.md
34-DESIGN-IR-RUNTIME-V1.md
35-CANVAS-ENGINE-V1.md
36-ARTIFACT-ENGINE-V1.md
37-BRAND-RULES-V1.md
38-IDENTITY-ASSET-INTELLIGENCE-V1.md
39-IMAGE-PIPELINE-V1.md
40-VIDEO-PIPELINE-V1.md
41-EXPORT-PIPELINE-V1.md
42-VISUAL-CRITIC-V1.md
43-FRONTEND-ARCHITECTURE-V2.md
44-COLLABORATION-V1.md
45-BILLING-ADMIN-V1.md
46-OBSERVABILITY-LANGSMITH-V1.md
47-SRE-RECOVERY-V1.md
48-DEPLOYMENT-INFRASTRUCTURE-V2.md
49-PRODUCTION-ACCEPTANCE-V2.md
```

文档会和代码节点一起演进，不采用“文档写完再全部编码”的瀑布方式；但是任何核心协议实现前必须先冻结对应 Spec。

---

# 35. 当前状态

```text
NODE-00 Master Implementation Plan
Status: COMPLETE

NEXT:
NODE-01 Architecture V2 Freeze
```

从 NODE-01 开始，所有节点完成后立即写入本 GitHub 仓库，并在提交后记录 commit SHA 与验收结果。

---

# 36. 参考的一手资料方向

实现期间持续优先使用官方来源：

- Lovart product/docs：`https://www.lovart.ai/`
- LangGraph / LangChain / Deep Agents / LangSmith：`https://docs.langchain.com/`
- Model Context Protocol：`https://modelcontextprotocol.io/`

其他模型、云服务、图片/视频 Provider 的资料在对应 Provider 节点重新联网核验，不依赖静态记忆。
