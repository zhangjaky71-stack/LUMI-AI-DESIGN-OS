# NODE-72 — Production Deployment & Infrastructure

> Phase: 9 Production Readiness  
> Status: **SOURCE IMPLEMENTED / CLOUD VALIDATION PENDING / GO-LIVE BLOCKED**  
> Priority: P0 / GO-LIVE  
> Depends on: NODE-66～71  
> Produces: IaC、生产网络/计算/数据/Agent Runtime、CI/CD、DNS/TLS、Secrets、Canary/Rollback与上线Runbook

---

## 0. Implementation Status — 2026-08-15

NODE-72 的 **Production deployment source baseline 已实现**，但真实 Production Definition of Done 尚未满足。

已落地的源码控制面包括：

- AWS Terraform reference deployment；
- Staging/Production 同模块、独立账号/状态参数模型；
- `core -> migration -> app` 三阶段独立 Terraform state；
- VPC public/private/data 三层子网与 3 AZ production contract；
- private RDS PostgreSQL / Redis / RabbitMQ data plane；
- KMS、private/versioned S3、Secrets Manager metadata containers；
- ECS/Fargate private tasks、per-service task/execution roles、Cloud Map；
- API 真实端口 8000；
- API 双 target group + ECS-native 5% canary + bake + alarm rollback；
- internal/headless services rolling + circuit-breaker rollback；
- Alembic migration-only DB credential + PostgreSQL advisory migration lock；
- pre-deploy RDS snapshot、one-shot migration task、exit-code gate；
- exact NODE-71 decision / RC SHA / version / migration head / image digest deployment gate；
- GitHub Environment + OIDC production deployment workflow；
- Secret `AWSCURRENT` readiness、ECS steady-state evidence、read-only production smoke；
- immutable Production deployment evidence archive；
- dependency-free deployment/IaC contract validator + Terraform static validation workflow。

当前仍是 **GO-LIVE BLOCKED**，因为以下事实尚未被真实运行证据证明：

- NODE-71 尚无真实 Production-like Staging `passed=true` RC；
- Production AWS 资源尚未由本节点证据实际 provision；
- 六个目标 runtime 尚未全部证明真实 production transport/entrypoint + reproducible build/promotion pipeline；
- Secret values、商业 provider 配额、DNS/TLS、billing/email/support 依赖尚未形成真实 Production evidence；
- canary/alarm rollback、post-promotion rollback、autoscale/restart、backup/restore 尚未真实演练；
- Sandbox production egress isolation 尚待 NODE-66 threat-model 对照验证；
- platform-wide daily provider-dollar hard stop 尚未证明为 durable runtime control；
- NODE-68/69/70/71 的 Production-like runtime evidence 仍未全部完成；
- GitHub hosted Actions 仍可能受账户 Billing/spending-limit 外部阻塞影响，NODE-72 必须以自己的 workflow 直接证据定性。

因此，本文件第 20 节 Production 验收项在真实证据产生前全部保持未勾选。

详细证据状态：

```text
docs/release-evidence/NODE-72-PRODUCTION-DEPLOYMENT-RELEASE-EVIDENCE.md
```

## 1. 目标

把通过Staging的同一Release Candidate部署到真实生产环境。Production选型必须优先“可管理、可恢复、可扩展”，而不是为了架构炫技过早引入复杂Kubernetes平台。

## 2. Reference Deployment

首个Production推荐采用AWS托管参考拓扑（最终实施时基于地区、价格和账户可用性复核）：

```text
DNS / TLS
   ↓
CDN / WAF
   ↓
Load Balancer
   ↓
ECS/Fargate services
├─ Web/API
├─ Agent Runtime API/Workers
├─ Model Gateway
├─ Tool Gateway
├─ Media Workers
└─ Sandbox Control Plane

Data
├─ RDS PostgreSQL Multi-AZ
├─ Managed Redis
├─ Managed RabbitMQ / compatible broker
├─ S3 Object Storage
└─ Secrets Manager/KMS
```

ECS/Fargate适合运行容器而无需自行管理宿主机；RDS PostgreSQL支持backup/PITR及Multi-AZ高可用。Kubernetes保留为规模/企业条件触发，而不是首发强制。

## 3. LangGraph / Agent Server Decision Gate

Production实现时对两种方案做最后Benchmark/成本评估：

### A. LangSmith/LangGraph Standalone Agent Server

优点：现成 persistence/task queue/streaming/runtime；可把API与queue workers拆分伸缩。

### B. LUMI自有 Agent Runtime

优点：与现有TaskGraph/Cost/Security边界控制更直接。

无论选择哪种：业务Project/Artifact/Billing DB仍由LUMI拥有；Agent Server不能成为唯一业务真相。

LangSmith官方当前支持managed、standalone与self-hosted deployment；standalone可把API和queue worker分离，适合Production自托管。最终决策写ADR，不在文档阶段锁死商业计划依赖。

## 4. Environments

```text
dev
staging
production
```

独立：accounts/projects/VPC/DB/buckets/secrets。绝不让Staging写Production bucket/database。

## 5. IaC

Terraform/OpenTofu选其一冻结。当前 NODE-72 source baseline 已冻结 Terraform，并按职责拆分为：

```text
infra/iac/modules/
network
storage
data
secrets
compute
edge
platform-core
platform-app
migration-runner
```

所有production手工console修改视为drift，紧急变更后必须回写IaC。

## 6. Network

- public: CDN/ALB only；
- private: API internal services/data；
- DB/Redis/Broker不公网；
- egress NAT/proxy policy；
- Sandbox更加严格的网络隔离；
- Tool Gateway作为外部访问集中点之一。

> 当前 source baseline 中 Sandbox 仍与普通 application tasks 共用 app security group。Production egress 隔离必须在真实环境验收前补强/审核，不能因为主网络已 private 就视为完成。

## 7. Compute

独立service scaling，当前 IaC 目标部署边界为：

```text
api
agent-runtime
model-gateway
tool-gateway
worker-media
sandbox-runtime
```

不是所有代码一个容器，也不是几十个无意义微服务。仓库中存在某个 Python package 也不等价于该 runtime 已具备独立 production transport/server/image；这必须通过 Staging image evidence 证明。

## 8. Database

Production：

- PostgreSQL managed；
- Multi-AZ/HA；
- encrypted；
- PITR；
- parameter/connection pool；
- migration job独立执行；
- app role与migration role分离。

当前 source baseline 还增加：pre-deploy snapshot、migration one-shot task、Alembic advisory lock、migration exit-code gate。

## 9. Redis / Broker

Managed HA能力按launch规模选择。Broker durable queues；Redis即使丢cache也能correctness恢复。Network ACL/credentials独立。

## 10. Object Storage

- private buckets；
- versioning；
- lifecycle；
- encryption；
- CORS最小化；
- CDN只通过受控private delivery；
- uploads/exports/sandbox分prefix或bucket权限。

当前 Terraform 将 assets / exports / sandbox 分 bucket，并统一使用 private access、versioning、KMS 与 TLS-only policy。

## 11. Secrets / IAM

Workload identity/task role优先；Secrets Manager存provider/API credentials。每service最小权限。例如Media Worker不需要Billing secret。

NODE-72 Terraform 只创建 Secret container，不把真实 Secret Version 写入 Terraform state；Production workflow 在 migration 前要求所需 Secrets 均具有 `AWSCURRENT`。

## 12. Container Supply Chain

- multi-stage builds；
- minimal base；
- immutable tag + digest；
- vulnerability scan；
- SBOM；
- ECR/registry private；
- release image从Staging promote，不Production重新“随手build”。

当前 deployment gate 已强制 immutable digest，但六个 runtime 的完整 reproducible build / scan / SBOM / promote pipeline 仍是 STOP SHIP，不能把“manifest 能填 digest”当作镜像供应链已经完成。

## 13. CI/CD

```text
merge main
→ unit/integration/security
→ build image
→ SBOM/scan/sign optional
→ deploy staging
→ NODE-70/71 gates
→ manual/controlled production approval
→ canary
→ health/SLO
→ promote
```

NODE-72 已实现 source-level Staging/Production Terraform workflows 与 Production exact-RC gate，但真实云端执行仍待证据。

## 14. Database Migration

Deployment前/中独立one-shot migration job：

- acquire advisory migration lock；
- backup/readiness；
- expand-compatible；
- fail stops rollout；
- contract migration延后。

当前实现顺序明确冻结为：

```text
core
→ Secret readiness
→ pre-deploy snapshot
→ migration stack
→ one-shot Alembic / exit=0
→ app stack
```

避免首次部署时 application services 在 schema migration 之前抢跑。

## 15. Canary / Rollback

Production总体发布策略：

```text
small cohort
→ health/quality/cost observation
→ controlled promotion
```

Public API 基础设施层当前实现 AWS ECS-native：

```text
5% green
→ 10-minute bake
→ 100% if healthy
```

并通过 green-target 5xx / unhealthy alarms rollback。更细的 25/50 阶段可用于 Agent/AI config aliases/feature flags，不应把基础设施 5%→100% canary 误述为已经完成所有 AI/config progressive rollout。

Rollback runbook必须包含DB compatibility；真实 rollback drill 未执行前 NODE-72 不可 COMPLETE。

## 16. DNS / TLS / WAF

- automated certificate；
- HTTPS only；
- HSTS after verified；
- WAF/rate-limits；
- custom domain；
- no direct public service task IP。

用户必须在此阶段完成无法由代码代办的域名/云账号/支付/商业API账号授权；在此之前工程使用mock/staging继续完成。

## 17. Production Readiness Check

上线前：

```text
backups verified
alerts tested
on-call contacts/runbooks
provider quotas
billing webhooks
email domain
storage lifecycle
security gates
cost ceilings
support/admin access
```

Source files只定义这些要求，不能替代真实运行证据。

## 18. First-Day Controls

初次生产采用保守limit：

- org/run generation并发；
- video数量；
- daily provider spend cap；
- invite/user rate limits；
- feature flags逐步开启。

防未知流量造成denial-of-wallet。

当前已有 WAF、ECS min/max capacity、request-level model budget 与 Billing credit/usage 基础；但 **platform-wide daily provider-dollar hard stop 尚未被证明为 durable runtime enforcement**，所以 manifest 中的 daily spend 数字不能单独算验收通过。

## 19. Tests

- IaC plan/apply staging；
- network reachability negative；
- secret least privilege；
- migration rollback-compatible；
- canary；
- service restart；
- autoscale；
- backup alarm；
- production smoke无真实用户破坏。

Source CI 已准备 contract/static Terraform validation；上述云端测试仍需真实执行。

## 20. 验收标准

- [ ] Production全部由IaC可重建关键资源。
- [ ] DB/Redis/Broker private。
- [ ] RDS/等价DB HA+PITR。
- [ ] Secrets最小权限。
- [ ] Staging image promote到Production。
- [ ] Canary/rollback实测。
- [ ] Alerts/backups/security gate ready。
- [ ] 外部账号依赖明确完成或对应功能关闭。

> 以上均为 Production runtime acceptance。Source implementation 不自动勾选任何一项。

## 21. Definition of Done

```text
production infrastructure provisioned
+ RC deployed via CI/CD
+ canary successful
+ smoke/SLO green
+ rollback path verified
```

当前：**NOT DONE / GO-LIVE BLOCKED**。

下一节点：NODE-73 Final Acceptance。
