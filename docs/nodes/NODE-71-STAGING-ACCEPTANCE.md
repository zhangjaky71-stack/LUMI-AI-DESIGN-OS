# NODE-71 — Staging End-to-End Acceptance

> Phase: 9 Production Readiness  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / GO-LIVE GATE  
> Depends on: NODE-52～70  
> Produces: Production-like Staging、完整E2E验收、Release Candidate报告与缺口清单

---

## 1. 目标

在Production前，用尽可能接近生产的环境完成一次“真实产品”验收：不是单元测试通过，而是从注册到项目、Agent、Canvas、生成、编辑、品牌、版本、导出、恢复、计费、安全全部贯通。

## 2. Environment Parity

Staging应与Production保持：

```text
same container images
same deployment topology class
same DB engine/major
same broker/object interfaces
same migrations
same auth/security headers
same Agent/Model Gateway code
```

规模可以小，架构不能完全不同。

## 3. Test Accounts

建立：

```text
Org A owner/editor/viewer
Org B owner
Platform ops account
Billing test org
```

用于tenant/security矩阵。禁止使用真实客户生产数据。

## 4. Provider Modes

- MockProvider：大规模/故障注入；
- provider sandbox/test mode；
-少量真实生产候选模型做quality acceptance。

商业Key缺失的能力标BLOCKED_EXTERNAL，不得伪装PASS；其他工程仍全部验收。

## 5. Golden E2E — Brand Project

输入：

```text
“为一家精品咖啡品牌完成市场研究、品牌方向、Logo/视觉体系、包装、菜单、海报、社媒素材和短视频。”
```

流程必须出现：

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

## 6. Golden E2E — Precision Edit

在第二张海报执行：

```text
“产品和Logo不要动，二维码位置大小不变；背景改成黑色，标题缩小15%。”
```

必须证明：

- Title结构化size变化；
- background change；
- Product identity pass；
- Logo pass；
- QR payload/geometry/scannability pass；
- 新Artifact/Design version；
-旧版本可restore。

## 7. Resilience Scenarios

运行中：

- restart Agent Runtime；
- restart worker；
- provider 429/5xx；
- Redis restart；
- duplicate event；
- SSE disconnect；
- payment webhook duplicate；
-DB failover/restore rehearsal environment。

## 8. Security Scenarios

- cross-tenant IDs；
- unauthorized asset signed URL；
- malicious SVG；
- prompt injection web page；
- SSRF metadata URL；
- sandbox traversal；
- Admin unauthorized；
- expired approval。

## 9. Cost / Billing

每个生成/修复有Cost Ledger；预算不足阻断；billing test credits不重复；cost summary与provider usage样本对账。

## 10. Performance

运行 NODE-69 launch profile；Staging小规格时按比例解释，不得只说“感觉快”。

## 11. Browser Acceptance

Chrome/Edge主目标；Safari按可用设备/云browser验证核心查看编辑流程。中文输入法/字体/上传/下载都测试。

## 12. Data Lifecycle

- Project archive/restore；
-Asset delete retention；
-Vector index delete；
-Audit；
-Export expiry；
-Backup restore。

## 13. Acceptance Report

每项：

```text
ID
scenario
expected
actual
evidence screenshot/log/trace/ref
status PASS/FAIL/BLOCKED_EXTERNAL
owner
severity
```

## 14. Exit Criteria

- Critical/High product/security failures = 0。
- 所有P0 acceptance PASS。
- 外部账号依赖若仍blocked，Production不得宣称对应功能可用。
- Recovery/perf/security报告完成。

## 15. Definition of Done

```text
staging RC deployed
+ golden E2E passed
+ security/resilience/performance gates passed
+ acceptance report approved
```

下一节点：NODE-72 Production Deployment。
