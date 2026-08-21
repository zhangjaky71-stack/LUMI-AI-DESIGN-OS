# NODE-71 — Staging End-to-End Acceptance

> Phase: 9 Production Readiness  
> Status: **ACCEPTANCE HARNESS + SOURCE DEPLOYMENT CONTRACTS IMPLEMENTED / STAGING RC NOT ACCEPTED / GO-LIVE BLOCKED**  
> Priority: P0 / GO-LIVE GATE  
> Depends on: NODE-52～70  
> Produces: Production-like Staging、完整 E2E 验收、Release Candidate 报告与缺口清单

---

## 1. 目标

在 Production 前，用尽可能接近生产的环境完成一次“真实产品”验收：不是单元测试通过，而是从注册到项目、Agent、Canvas、生成、编辑、品牌、版本、导出、恢复、计费、安全全部贯通。

NODE-71 当前已经实现验收控制面、Staging IaC 源码契约、不可变 Runtime Image 绑定与证据契约；**真实 production-like Staging 的 exact RC 尚未形成可审计 `passed=true` 证据**，所以本节点不能标记 COMPLETE。

## 2. Environment Parity

Staging 必须证明：

```text
same immutable container image set
same deployment topology class
same DB engine/major
same broker/object interfaces
same migrations
same auth/security code path
same Agent/Tool/Model Gateway code identity
production-class observability interfaces
isolated staging secrets
```

权威契约：`staging/acceptance/environment-parity-v1.json`。

仓库当前已存在 canonical IaC：

```text
infra/iac/environments/staging/core
infra/iac/environments/staging/migration
infra/iac/environments/staging/app
infra/iac/modules/*
```

因此旧的“仓库没有 production-like Staging IaC”判断已经失效。当前 blocker 不是缺少 IaC 源码，而是：Terraform trusted execution、真实 apply、exact RC 镜像部署、live parity/E2E/安全/恢复/性能/AI evidence 尚未产生。

## 3. Private Model Gateway Staging Boundary

NODE-71 的 `source-contract` 现在直接执行：

```text
scripts/validate_private_model_gateway_deployment_contract.py
```

Staging source gate 必须证明：

- `model-gateway.<env>.lumi.internal:8080` 私有服务发现 URL 保持存在；
- Staging 只有 `model-gateway` 获得 `providers/model` / `providers/media` secrets；
- `agent-runtime` 与 `worker-media` 只获得 private Model Gateway URL + internal HMAC secret 用于模型访问；
- ECS execution IAM/task definition 只注入每个 service 声明的 `secret_arns`；
- Hosted Agent/Image/Video client 继续从 private Gateway env 构造；
- Runtime-image provenance 包含 private client / Hosted Gateway 实现源码；
- Model Gateway、Production IaC、Staging Acceptance、Final Acceptance 四条 workflow 都必须保留并 syntax-gate 该 contract。

这是一条**源码/部署配置边界**，不是 deployed Staging PASS。真实 ECS task definition、exact image digest、secret injection 与实际 signed private Gateway 调用仍必须在 Staging 证据中证明。

## 4. Test Accounts

证据模板要求：

```text
Org A owner/editor/viewer
Org B owner
Platform ops account
Billing test org
```

禁止真实客户生产数据；不得把密码、cookie、token 写入验收报告。

## 5. Provider Modes

必须明确记录：

- MockProvider：大规模/故障注入；
- provider sandbox/test mode；
- 少量真实 production-candidate 模型做 quality acceptance。

商业 Key/账号缺失可标 `BLOCKED_EXTERNAL`，但只有 manifest 明确允许 external dependency 的场景才能使用；P0 即使 external blocked 仍阻止 go-live。

## 6. Golden E2E — Brand Project

Canonical input：

> 为一家精品咖啡品牌完成市场研究、品牌方向、Logo/视觉体系、包装、菜单、海报、社媒素材和短视频。

必须出现：

```text
Project
→ Structured Brief
→ Research with sources
→ Strategy
→ Creative directions
→ Approval
→ Design/Generation
→ Canvas
→ Brand rules
→ Critic/Repair
→ Versions
→ Export
```

场景 ID：`E2E-01`。

## 7. Golden E2E — Precision Edit

Canonical edit：

> 产品和 Logo 不要动，二维码位置大小不变；背景改成黑色，标题缩小 15%。

必须证明：

- Title 结构化 size 变化；
- background change；
- Product identity pass；
- Logo pass；
- QR payload/geometry/scannability pass；
- 新 Artifact/Design version；
- 旧版本可 restore。

场景 ID：`E2E-02`。

## 8. Acceptance Manifest

权威清单：`staging/acceptance/manifest-v1.json`。

冻结场景覆盖：

```text
Environment / Accounts
Golden E2E / Precision Edit
Resilience
Security
Billing / Cost
Performance
AI Release
Browser / Chinese IME / Fonts / Upload / Download
Data Lifecycle / Backup Restore
Observability
```

每项必须记录：

```text
status PASS/FAIL/BLOCKED_EXTERNAL/NOT_RUN
actual
evidence_ref
owner
external_reason (BLOCKED_EXTERNAL only)
```

## 9. Fail-closed RC Gate

实现：`scripts/staging-acceptance-gate.py`。

规则：

- P0 只接受有证据的 PASS；
- PASS 缺 `actual/evidence_ref/owner` 无效；
- BLOCKED_EXTERNAL 永远不是 PASS 替代；
- 非 external 场景禁止 BLOCKED_EXTERNAL；
- open Critical/High issue = BLOCK；
- 所有 required parity 必须 PASS；
- production customer data 禁止；
- staging secrets 必须隔离；
- Engineering/Security/Product/Release Owner 必须全部 APPROVED；
- RC Git SHA 必须是 exact 40-char SHA；
- base URL 必须 HTTPS。

输出 machine JSON + Markdown + deterministic decision ID。

## 10. Read-only Preflight

实现：`scripts/staging-preflight.py`。

只 GET：

```text
/health/live
/health/ready
/version
```

要求：HTTPS、exact host ACK、`LUMI_STAGING_ENV_ACK=staging`、不跟随 redirect、RC version 一致、核心 security headers 存在。

## 11. Contract Drills

实现：`scripts/validate_staging_acceptance_contract.py`。

Source contract 必须证明：

- empty evidence 不能 PASS；
- clean synthetic fixture 可通过控制逻辑；
- P0 NOT_RUN 阻断；
- fake PASS 无证据阻断；
- internal scenario 不能滥用 BLOCKED_EXTERNAL；
- external P0 blocked 仍阻断；
- open Critical 阻断；
- parity failure 阻断。

这些只是 control-plane drill，不等于真实 Staging PASS。

## 12. Staging Acceptance CI

`.github/workflows/staging-acceptance-gate.yml` 当前关键门槛：

```text
source-contract
  -> staging acceptance contract
  -> private Model Gateway deployment contract
  -> immutable evidence artifact drills
  -> API/runtime-image/provenance/media E2E source contracts
  -> Python/JSON syntax

canonical-lock-gate
  -> exact workspace membership in uv.lock
  -> uv lock --check
  -> uv sync --all-packages --frozen

remote-read-only-preflight
  -> workflow_dispatch only

acceptance-decision
  -> workflow_dispatch + completed evidence + exact runtime image build run
```

当前 `uv.lock` 仍存在 6-package workspace drift，因此 canonical-lock 不能宣称通过。不得手改 lockfile；必须由 canonical resolver workflow 生成。

## 13. Resilience / Security / Cost / Performance / AI

P0 仍包括：

- Agent Runtime / worker / Redis / provider failure / duplicate delivery / DB recovery；
- cross-tenant / signed URL / SVG / prompt injection / SSRF / sandbox / admin approval；
- Cost Ledger / paid-side-effect reservation / budget / credits / webhook idempotency / provider usage reconciliation；
- NODE-69 identified Staging launch profile；
- NODE-70 exact production-candidate AI release evidence。

不得把 source contract、fixture、MockProvider 或零步骤 CI 结果冒充 runtime acceptance。

## 14. Browser / Data Lifecycle

P0：Chrome、Edge、中文 IME、字体、上传下载、Project archive/restore、asset/vector deletion/retention/audit/export expiry、backup restore。

Safari 为 P1；设备/云 browser 不可用时允许诚实 `BLOCKED_EXTERNAL`，但不是 PASS。

## 15. Acceptance Report

Evidence 模板：`staging/acceptance/evidence-template.json`。

正式归档：`reports/staging-acceptance/<rc-sha>/`。

失败 decision 保留，不覆盖历史。

## 16. Exit Criteria

- [x] Versioned acceptance manifest 实现。
- [x] Environment parity contract 实现。
- [x] Fail-closed evaluator 实现。
- [x] Read-only remote preflight 实现。
- [x] Negative contract drills 实现。
- [x] Staging IaC source topology 实现。
- [x] Private Model Gateway Staging source gate 实现并与 Model/IaC/Final 互锁。
- [x] Staging Acceptance workflow 实现。
- [ ] Resolver-generated canonical `uv.lock` + frozen all-workspace graph PASS。
- [ ] Trusted Terraform validate/plan/apply PASS。
- [ ] Exact immutable RC image set deployed to production-like Staging。
- [ ] Environment parity 全部真实 PASS。
- [ ] Golden E2E 全部 PASS。
- [ ] Security/resilience/performance/AI runtime gates 全部 PASS。
- [ ] Critical/High open failures = 0。
- [ ] 所有 P0 acceptance 真实 PASS。
- [ ] Final approvals 完成。
- [ ] `decision.json` 对 exact RC 返回 `passed=true`。

## 17. Definition of Done

```text
exact RC images deployed
+ canonical dependency graph proven
+ environment parity proven
+ private Gateway/provider boundary proven in deployed tasks
+ golden E2E passed
+ security/resilience/performance/AI gates passed
+ all P0 evidenced PASS
+ acceptance report approved
+ exact RC decision passed
```

当前状态：**ACCEPTANCE HARNESS + SOURCE DEPLOYMENT CONTRACTS IMPLEMENTED / STAGING RC NOT ACCEPTED / GO-LIVE BLOCKED**。

详细执行计划：`docs/staging/NODE-71-STAGING-ACCEPTANCE-PLAN.md`  
Release Evidence：`docs/release-evidence/NODE-71-STAGING-ACCEPTANCE-RELEASE-EVIDENCE.md`

下一节点：NODE-72 Production Deployment。