# NODE-71 — Staging End-to-End Acceptance

> Phase: 9 Production Readiness  
> Status: **ACCEPTANCE HARNESS IMPLEMENTED / STAGING RC NOT DEPLOYED / GO-LIVE BLOCKED**  
> Priority: P0 / GO-LIVE GATE  
> Depends on: NODE-52～70  
> Produces: Production-like Staging、完整E2E验收、Release Candidate报告与缺口清单

---

## 1. 目标

在Production前，用尽可能接近生产的环境完成一次“真实产品”验收：不是单元测试通过，而是从注册到项目、Agent、Canvas、生成、编辑、品牌、版本、导出、恢复、计费、安全全部贯通。

NODE-71 当前已经实现验收控制面与证据契约；真实 production-like Staging 尚未部署，所以本节点不能标记 COMPLETE。

## 2. Environment Parity

Staging必须证明：

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

当前仓库已有local Compose/observability/recovery基础，但 `infra/terraform` 尚未提供production-like Staging部署，因此不得把local Compose宣称为Staging RC。

## 3. Test Accounts

证据模板要求：

```text
Org A owner/editor/viewer
Org B owner
Platform ops account
Billing test org
```

禁止真实客户生产数据；不得把密码、cookie、token写入验收报告。

## 4. Provider Modes

必须明确记录：

- MockProvider：大规模/故障注入；
- provider sandbox/test mode；
- 少量真实production-candidate模型做quality acceptance。

商业Key/账号缺失可标 `BLOCKED_EXTERNAL`，但只有manifest明确允许external dependency的场景才能使用；P0即使external blocked仍阻止go-live。

## 5. Golden E2E — Brand Project

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

场景ID：`E2E-01`。

## 6. Golden E2E — Precision Edit

Canonical edit：

> 产品和Logo不要动，二维码位置大小不变；背景改成黑色，标题缩小15%。

必须证明：

- Title结构化size变化；
- background change；
- Product identity pass；
- Logo pass；
- QR payload/geometry/scannability pass；
- 新Artifact/Design version；
- 旧版本可restore。

场景ID：`E2E-02`。

## 7. Acceptance Manifest

权威清单：`staging/acceptance/manifest-v1.json`。

当前冻结30个场景，覆盖：

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

## 8. Fail-closed RC Gate

实现：`scripts/staging-acceptance-gate.py`。

规则：

- P0只接受有证据的PASS；
- PASS缺 `actual/evidence_ref/owner` 无效；
- BLOCKED_EXTERNAL永远不是PASS替代；
- 非external场景禁止BLOCKED_EXTERNAL；
- open Critical/High issue = BLOCK；
- 所有required parity必须PASS；
- production customer data禁止；
- staging secrets必须隔离；
- Engineering/Security/Product/Release Owner必须全部APPROVED；
- RC Git SHA必须是exact 40-char SHA；
- base URL必须HTTPS。

输出machine JSON + Markdown + deterministic decision ID。

## 9. Read-only Preflight

实现：`scripts/staging-preflight.py`。

只GET：

```text
/health/live
/health/ready
/version
```

要求：HTTPS、exact host ACK、`LUMI_STAGING_ENV_ACK=staging`、不跟随redirect、RC version一致、核心security headers存在。

## 10. Contract Drills

实现：`scripts/validate_staging_acceptance_contract.py`。

Source contract必须证明：

- empty evidence不能PASS；
- clean synthetic fixture可通过控制逻辑；
- P0 NOT_RUN阻断；
- fake PASS无证据阻断；
- internal scenario不能滥用BLOCKED_EXTERNAL；
- external P0 blocked仍阻断；
- open Critical阻断；
- parity failure阻断。

这些只是control-plane drill，不等于真实Staging PASS。

## 11. Staging Acceptance CI

`.github/workflows/staging-acceptance-gate.yml`：

- `source-contract`：dependency-free控制逻辑；
- `canonical-lock-gate`：`uv sync --frozen`，不绕过root lock问题；
- `remote-read-only-preflight`：仅workflow_dispatch；
- `acceptance-decision`：仅workflow_dispatch + completed evidence path；
- artifacts：preflight/decision报告；
- workflow-dispatch输入通过environment传给shell，避免直接source interpolation。

## 12. Resilience Scenarios

P0包括：

- Agent Runtime restart；
- worker restart；
- provider 429/5xx；
- Redis restart；
- duplicate event/webhook + SSE reconnect；
- DB failover-equivalent / isolated restore rehearsal。

## 13. Security Scenarios

P0包括：

- cross-tenant IDs/objects；
- unauthorized signed URL；
- malicious SVG/upload；
- indirect prompt injection；
- SSRF metadata/private target；
- sandbox traversal/escape；
- unauthorized Admin / expired approval。

Security Critical failure = STOP SHIP。

## 14. Cost / Billing

P0 `BILL-01` 必须验证：

- Cost Ledger；
- reservation before paid side effect；
- budget不足阻断；
- test credit不重复；
- duplicate webhook idempotent；
- provider usage样本对账。

## 15. Performance / AI Release

- `PERF-01`：NODE-69 Profile G必须在identified Staging RC上实测；
- `AI-01`：production-candidate quality acceptance；
- `AI-02`：NODE-70必须使用真实production baseline/candidate evidence生成release decision。

不得把source contract或fixture结果冒充runtime acceptance。

## 16. Browser / Data Lifecycle

P0：Chrome、Edge、中文IME、字体、上传下载、Project archive/restore、asset/vector deletion/retention/audit/export expiry、backup restore。

Safari为P1；设备/云browser不可用时允许诚实 `BLOCKED_EXTERNAL`，但不是PASS。

## 17. Acceptance Report

Evidence模板：`staging/acceptance/evidence-template.json`。

正式归档：`reports/staging-acceptance/<rc-sha>/`。

失败decision保留，不覆盖历史。

## 18. Exit Criteria

- [x] Versioned acceptance manifest实现。
- [x] Environment parity contract实现。
- [x] Fail-closed evaluator实现。
- [x] Read-only remote preflight实现。
- [x] Negative contract drills实现。
- [x] Staging Acceptance workflow实现。
- [ ] Production-like Staging RC deployed。
- [ ] Environment parity全部真实PASS。
- [ ] Golden E2E全部PASS。
- [ ] Security/resilience/performance/AI runtime gates全部PASS。
- [ ] Critical/High open failures = 0。
- [ ] 所有P0 acceptance真实PASS。
- [ ] Final approvals完成。
- [ ] `decision.json` 对exact RC返回 `passed=true`。

## 19. Definition of Done

```text
staging RC deployed
+ golden E2E passed
+ security/resilience/performance/AI gates passed
+ all P0 evidenced PASS
+ acceptance report approved
+ exact RC decision passed
```

当前状态：**ACCEPTANCE HARNESS IMPLEMENTED / STAGING RC NOT DEPLOYED / GO-LIVE BLOCKED**。

详细执行计划：`docs/staging/NODE-71-STAGING-ACCEPTANCE-PLAN.md`  
Release Evidence：`docs/release-evidence/NODE-71-STAGING-ACCEPTANCE-RELEASE-EVIDENCE.md`

下一节点：NODE-72 Production Deployment。
