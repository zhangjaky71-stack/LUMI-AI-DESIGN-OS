# LUMI AI Design OS — NODE Documentation Index

> Architecture Baseline: **LUMI AI Design OS — Architecture V2**  
> Documentation Status: **NODE-00～NODE-73 ALL SPECIFIED**  
> Implementation Status: **NODE-02 engineering COMPLETE; next engineering node is NODE-03**  
> Rule: **SPECIFIED ≠ IMPLEMENTED**. 每个工程 Node 必须完成代码、测试、验收和 GitHub 提交后才能改为 `COMPLETE`。

---

## 1. 使用方法

后续实施严格按 Node 顺序和依赖执行。每进入一个 Node：先阅读对应详细文档，再检查依赖 Node 是否已经 `COMPLETE`，然后实现代码/迁移/配置/测试，运行文档中的 Acceptance Criteria，生成必要的验收证据，提交 GitHub，最后更新本索引状态。

标准状态：

```text
SPECIFIED
→ IN_PROGRESS
→ IMPLEMENTED
→ VALIDATING
→ COMPLETE
```

出现阻塞：

```text
BLOCKED_EXTERNAL   # 只能由用户/外部供应商完成的账号、商业Key、域名、支付签约等
BLOCKED_TECHNICAL  # 技术故障
```

`BLOCKED_EXTERNAL` 只能阻塞依赖该外部能力的真实集成测试，不能成为停止其它工程开发的理由；使用 Mock/Fake/Local Adapter 继续推进。

---

# Phase -1 — Engineering Foundation

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-00 | [Master Implementation Plan](00-MASTER-IMPLEMENTATION-PLAN.md) | COMPLETE (Docs) | 总实施蓝图、73节点路线 |
| NODE-01 | [Architecture V2 Freeze](01-ARCHITECTURE-V2-FREEZE.md) | COMPLETE / FROZEN | 系统边界、技术基线、ADR |
| NODE-02 | [Repository Bootstrap](nodes/NODE-02-REPOSITORY-BOOTSTRAP.md) | **COMPLETE** | Monorepo、lockfiles、Web/API/Agent/Worker scaffold；CI Run `31584394850` PASS |
| NODE-03 | [Local Infrastructure](nodes/NODE-03-LOCAL-INFRASTRUCTURE.md) | SPECIFIED | PostgreSQL/Redis/RabbitMQ/MinIO/Mailpit |
| NODE-04 | [CI Foundation](nodes/NODE-04-CI-FOUNDATION.md) | SPECIFIED | GitHub Actions、质量/安全基础门禁 |

# Phase 0 — Benchmark Before Build

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-05 | [Benchmark Harness](nodes/NODE-05-BENCHMARK-HARNESS.md) | SPECIFIED | Eval runner/dataset/grader/release gate |
| NODE-06 | [Lovart Capability Matrix](nodes/NODE-06-LOVART-CAPABILITY-MATRIX.md) | SPECIFIED | 竞品公开能力与LUMI验收映射 |
| NODE-07 | [Model Provider Matrix](nodes/NODE-07-MODEL-PROVIDER-MATRIX.md) | SPECIFIED | 模型能力/成本/延迟/质量矩阵 |
| NODE-08 | [Canvas Technology Spike](nodes/NODE-08-CANVAS-TECHNOLOGY-SPIKE.md) | SPECIFIED | PixiJS Canvas性能与可行性验证 |

# Phase 1 — Domain & Contracts

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-09 | [Domain Model](nodes/NODE-09-DOMAIN-MODEL.md) | SPECIFIED | Bounded Context、实体、状态机、不变量 |
| NODE-10 | [Database Schema](nodes/NODE-10-DATABASE-SCHEMA.md) | SPECIFIED | PostgreSQL schema/Alembic/索引/Outbox |
| NODE-11 | [API Contract](nodes/NODE-11-API-CONTRACT.md) | SPECIFIED | REST `/api/v1`、OpenAPI、TS Client |
| NODE-12 | [Event Protocol](nodes/NODE-12-EVENT-PROTOCOL.md) | SPECIFIED | Event Envelope、Outbox/Inbox、Async schema |
| NODE-13 | [Design IR V1](nodes/NODE-13-DESIGN-IR.md) | SPECIFIED | Design IR/Operation JSON Schema |
| NODE-14 | [Constraint Engine V1](nodes/NODE-14-CONSTRAINT-ENGINE.md) | SPECIFIED | Hard/Soft约束、Pre/Postflight规范 |
| NODE-15 | [Artifact / Version / Provenance](nodes/NODE-15-ARTIFACT-VERSION-PROVENANCE.md) | SPECIFIED | 不可变版本、Branch、Lineage、Rights |

# Phase 2 — Runtime Foundation

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-16 | [Authentication & Tenant](nodes/NODE-16-AUTH-TENANT.md) | SPECIFIED | Auth、Session、Org/Workspace、RBAC |
| NODE-17 | [Project Core](nodes/NODE-17-PROJECT-CORE.md) | SPECIFIED | Project/Brief生命周期 |
| NODE-18 | [Asset Storage](nodes/NODE-18-ASSET-STORAGE.md) | SPECIFIED | Presigned Upload、验证、Preview、Rights |
| NODE-19 | [Queue & Event Runtime](nodes/NODE-19-QUEUE-EVENT-RUNTIME.md) | SPECIFIED | RabbitMQ/Celery/Outbox Consumer/DLQ |
| NODE-20 | [Idempotency & Side Effects](nodes/NODE-20-IDEMPOTENCY-SIDE-EFFECTS.md) | SPECIFIED | 幂等Operation、Provider reconciliation |
| NODE-21 | [Sandbox Runtime](nodes/NODE-21-SANDBOX-RUNTIME.md) | SPECIFIED | 隔离执行、资源/网络/文件权限 |

# Phase 3 — AI Infrastructure

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-22 | [Model Gateway](nodes/NODE-22-MODEL-GATEWAY.md) | SPECIFIED | 统一模型调用、Adapter、Routing/Fallback |
| NODE-23 | [Capability Registry](nodes/NODE-23-CAPABILITY-REGISTRY.md) | SPECIFIED | 模型能力/价格/Benchmark Registry |
| NODE-24 | [Provider Health](nodes/NODE-24-PROVIDER-HEALTH.md) | SPECIFIED | Health/Circuit Breaker/Fallback signals |
| NODE-25 | [Tool Gateway](nodes/NODE-25-TOOL-GATEWAY.md) | SPECIFIED | Tool Registry、权限、HITL、审计 |
| NODE-26 | [MCP Integration](nodes/NODE-26-MCP-INTEGRATION.md) | SPECIFIED | MCP Client/Server Registry/Policy Adapter |
| NODE-27 | [Cost Ledger](nodes/NODE-27-COST-LEDGER.md) | SPECIFIED | Cost/Usage/Budget/Quota基础 |

# Phase 4 — Agent Intelligence

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-28 | [LangGraph Control Plane](nodes/NODE-28-LANGGRAPH-CONTROL-PLANE.md) | SPECIFIED | Checkpoint/Interrupt/Resume/Graph版本 |
| NODE-29 | [Deep Agents Runtime](nodes/NODE-29-DEEP-AGENTS-RUNTIME.md) | SPECIFIED | Planning/Subagents/Skills/Filesystem/Sandbox |
| NODE-30 | [Agent Registry](nodes/NODE-30-AGENT-REGISTRY.md) | SPECIFIED | AgentDefinition版本与发布 |
| NODE-31 | [Skill Registry](nodes/NODE-31-SKILL-REGISTRY.md) | SPECIFIED | 可复用Skills、依赖与Eval |
| NODE-32 | [Workflow / Recipe Engine](nodes/NODE-32-WORKFLOW-RECIPE-ENGINE.md) | SPECIFIED | Recipe DSL、Approval/Parallel/Quality Gate |
| NODE-33 | [Task Graph](nodes/NODE-33-TASK-GRAPH.md) | SPECIFIED | 持久DAG、Scheduler、Retry/Cancel |
| NODE-34 | [Context Engine](nodes/NODE-34-CONTEXT-ENGINE.md) | SPECIFIED | Selection/Trust/Compression/Prompt Compiler |
| NODE-35 | [Memory Engine](nodes/NODE-35-MEMORY-ENGINE.md) | SPECIFIED | User/Project/Brand/Agent Memory |
| NODE-36 | [Knowledge Engine](nodes/NODE-36-KNOWLEDGE-ENGINE.md) | SPECIFIED | Ingestion/Hybrid Retrieval/Citations |
| NODE-37 | [Agent Team V1](nodes/NODE-37-AGENT-TEAM.md) | SPECIFIED | Director + 16 specialized agents |

# Phase 5 — Design Intelligence

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-38 | [Design IR Runtime](nodes/NODE-38-DESIGN-IR-RUNTIME.md) | SPECIFIED | Parser/Operations/Migrations/Canonical Hash |
| NODE-39 | [Constraint Validator](nodes/NODE-39-CONSTRAINT-VALIDATOR.md) | SPECIFIED | Runtime Pre/Postflight、QR/Region validators |
| NODE-40 | [Canvas Engine](nodes/NODE-40-CANVAS-ENGINE.md) | SPECIFIED | PixiJS Infinite Canvas Runtime |
| NODE-41 | [Canvas Compiler](nodes/NODE-41-CANVAS-COMPILER.md) | SPECIFIED | IR→Scene Graph、Incremental Compile |
| NODE-42 | [Artifact Engine](nodes/NODE-42-ARTIFACT-ENGINE.md) | SPECIFIED | Version/Branch/Lineage/Restore/GC |
| NODE-43 | [Brand Rules Engine](nodes/NODE-43-BRAND-RULES-ENGINE.md) | SPECIFIED | Brand Tokens/Rules/Compliance |
| NODE-44 | [Identity Engine](nodes/NODE-44-IDENTITY-ENGINE.md) | SPECIFIED | Product/Logo Identity验证 |
| NODE-45 | [Asset Intelligence](nodes/NODE-45-ASSET-INTELLIGENCE.md) | SPECIFIED | OCR/Embedding/Search/Duplicate/Resolver |

# Phase 6 — Generation & Quality

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-46 | [Image Generation](nodes/NODE-46-IMAGE-GENERATION.md) | SPECIFIED | 多模型图片生成Pipeline |
| NODE-47 | [Image Edit](nodes/NODE-47-IMAGE-EDIT.md) | SPECIFIED | Local Edit/Mask/Protected Content |
| NODE-48 | [Video Generation](nodes/NODE-48-VIDEO-GENERATION.md) | SPECIFIED | Storyboard/Shot/Provider/FFmpeg |
| NODE-49 | [Export Engine](nodes/NODE-49-EXPORT-ENGINE.md) | SPECIFIED | PNG/JPEG/WebP/SVG/PDF/Batch |
| NODE-50 | [Visual Critic](nodes/NODE-50-VISUAL-CRITIC.md) | SPECIFIED | Design Quality Engine/Quality Gate |
| NODE-51 | [Auto Repair](nodes/NODE-51-AUTO-REPAIR.md) | SPECIFIED | 有界Repair Loop/质量回退 |

# Phase 7 — Frontend Product

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-52 | [App Shell](nodes/NODE-52-APP-SHELL.md) | SPECIFIED | Next.js Shell/Auth/Nav/API client |
| NODE-53 | [Projects UI](nodes/NODE-53-PROJECTS-UI.md) | SPECIFIED | Dashboard/New Project/Brief |
| NODE-54 | [AI Workspace](nodes/NODE-54-AI-WORKSPACE.md) | SPECIFIED | Chat + Canvas + Streaming + Approval |
| NODE-55 | [Infinite Canvas UI](nodes/NODE-55-INFINITE-CANVAS-UI.md) | SPECIFIED | Product Canvas UX/Autosave |
| NODE-56 | [Layers & Inspector](nodes/NODE-56-LAYERS-INSPECTOR.md) | SPECIFIED | Layer Tree/属性/Constraints |
| NODE-57 | [Agent Timeline](nodes/NODE-57-AGENT-TIMELINE.md) | SPECIFIED | Run/Task透明进度与错误 |
| NODE-58 | [Brand Kit UI](nodes/NODE-58-BRAND-KIT-UI.md) | SPECIFIED | Brand Kit管理/规则发布 |
| NODE-59 | [Versions UI](nodes/NODE-59-VERSIONS-UI.md) | SPECIFIED | Compare/Fork/Restore/Provenance |
| NODE-60 | [Export UI](nodes/NODE-60-EXPORT-UI.md) | SPECIFIED | Export settings/Progress/Downloads |

# Phase 8 — SaaS & Collaboration

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-61 | [Collaboration](nodes/NODE-61-COLLABORATION.md) | SPECIFIED | Presence/Comments/Realtime协作 |
| NODE-62 | [Approval Engine](nodes/NODE-62-APPROVAL-ENGINE.md) | SPECIFIED | Version-bound HITL Approval |
| NODE-63 | [Billing](nodes/NODE-63-BILLING.md) | SPECIFIED | Plans/Entitlements/Credits/Payment Adapter |
| NODE-64 | [Admin Console](nodes/NODE-64-ADMIN-CONSOLE.md) | SPECIFIED | 平台运维控制面 |
| NODE-65 | [Audit & Governance](nodes/NODE-65-AUDIT-GOVERNANCE.md) | SPECIFIED | Append-only Audit/Retention/Hold |

# Phase 9 — Production Readiness

| Node | 文档 | 状态 | 主要产物 |
|---|---|---|---|
| NODE-66 | [Security Hardening](nodes/NODE-66-SECURITY-HARDENING.md) | SPECIFIED | Threat Model/SAST/DAST/Agent red-team |
| NODE-67 | [Observability](nodes/NODE-67-OBSERVABILITY.md) | SPECIFIED | OTel/LangSmith/Dashboard/SLO/Alerts |
| NODE-68 | [Recovery & DR](nodes/NODE-68-RECOVERY-DR.md) | SPECIFIED | Backup/PITR/Run恢复/DR演练 |
| NODE-69 | [Performance & Scalability](nodes/NODE-69-PERFORMANCE-SCALABILITY.md) | SPECIFIED | Load/Soak/Capacity/Autoscaling |
| NODE-70 | [AI Regression Gate](nodes/NODE-70-AI-REGRESSION-RELEASE-GATE.md) | SPECIFIED | Baseline/Shadow/Canary/Rollback |
| NODE-71 | [Staging Acceptance](nodes/NODE-71-STAGING-ACCEPTANCE.md) | SPECIFIED | Production-like E2E验收 |
| NODE-72 | [Production Deployment](nodes/NODE-72-PRODUCTION-DEPLOYMENT.md) | SPECIFIED | IaC/Production/CI-CD/Canary |
| NODE-73 | [Final Acceptance](nodes/NODE-73-FINAL-ACCEPTANCE.md) | SPECIFIED / FINAL GATE | 最终产品级验收与证据包 |

---

# 2. 工程实施顺序

后续默认逐Node推进：

```text
Read Node Spec
→ Verify dependencies COMPLETE
→ Create implementation scope
→ Implement
→ Static checks
→ Unit tests
→ Integration/E2E/Security/Eval tests as required
→ Acceptance Criteria
→ Evidence / Report
→ Git commit
→ Update NODE-INDEX status
→ Next Node
```

除非某Node文档明确允许并行，不能为了速度跳过依赖。例如：不能跳过Design IR/Constraint合同直接硬写Canvas；不能跳过Idempotency直接让LangGraph调用付费Provider；不能跳过Benchmark就用主观演示宣布模型升级。

# 3. 每个 Node 的 GitHub 提交要求

完成工程实现后，至少：

```text
code/config/migrations
+ tests
+ docs updates
+ acceptance evidence
+ changelog/ADR if architecture changed
```

推荐commit：

```text
feat(...): implement ... (NODE-XX)
```

实现后在对应Node文档顶部追加：

```text
Implementation Status: COMPLETE
Implemented Commit: <sha>
Acceptance Report: <path>
Implemented At: <date>
```

# 4. 架构变更规则

NODE-01 Architecture V2 已冻结。实现过程中若发现必须改变一级边界：

```text
create ADR
→ explain problem/options/tradeoff
→ benchmark/security/cost evidence
→ approve ADR
→ update Architecture V2 + affected Node specs
→ then implement
```

禁止代码先偏离架构、文档以后再补。

# 5. 最终验收线

真正完成不是“NODE-73文档写完”，而是：

```text
NODE-02～72 engineering implementation COMPLETE
+ NODE-73 acceptance matrix PASS
+ Security PASS
+ Recovery PASS
+ Performance PASS
+ AI Regression PASS
+ Production Deployment PASS
```

最后才能标记：

# LUMI AI DESIGN OS — PRODUCT ACCEPTED
