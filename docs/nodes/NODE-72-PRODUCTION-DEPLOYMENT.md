# NODE-72 — Production Deployment & Infrastructure

> Phase: 9 Production Readiness  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0 / GO-LIVE  
> Depends on: NODE-66～71  
> Produces: IaC、生产网络/计算/数据/Agent Runtime、CI/CD、DNS/TLS、Secrets、Canary/Rollback与上线Runbook

---

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

Terraform/OpenTofu选其一冻结：

```text
infra/iac/modules/
network
compute
database
cache
broker
storage
secrets
observability
cdn
```

所有production手工console修改视为drift，紧急变更后必须回写IaC。

## 6. Network

- public: CDN/ALB only；
- private: API internal services/data；
- DB/Redis/Broker不公网；
- egress NAT/proxy policy；
- Sandbox更加严格的网络隔离；
- Tool Gateway作为外部访问集中点之一。

## 7. Compute

独立service scaling：

```text
web/api
agent-api
agent-workers
model-gateway
tool-gateway
media-image
media-video
export
```

不是所有代码一个容器，也不是几十个无意义微服务。

## 8. Database

Production：

- PostgreSQL managed；
- Multi-AZ/HA；
- encrypted；
- PITR；
- parameter/connection pool；
- migration job独立执行；
- app role与migration role分离。

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

## 11. Secrets / IAM

Workload identity/task role优先；Secrets Manager存provider/API credentials。每service最小权限。例如Media Worker不需要Billing secret。

## 12. Container Supply Chain

- multi-stage builds；
- minimal base；
- immutable tag + digest；
- vulnerability scan；
- SBOM；
- ECR/registry private；
- release image从Staging promote，不Production重新“随手build”。

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

## 14. Database Migration

Deployment前/中独立one-shot migration job：

- acquire advisory migration lock；
- backup/readiness；
- expand-compatible；
- fail stops rollout；
- contract migration延后。

## 15. Canary / Rollback

Production：

```text
5% or internal cohort
→ health/quality/cost check
→ 25/50/100
```

Web/API使用load balancer deployment策略；Agent config使用version aliases/feature flags。Rollback runbook包含DB compatibility。

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

## 18. First-Day Controls

初次生产采用保守limit：

- org/run generation并发；
- video数量；
- daily provider spend cap；
- invite/user rate limits；
- feature flags逐步开启。

防未知流量造成denial-of-wallet。

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

## 20. 验收标准

- [ ] Production全部由IaC可重建关键资源。
- [ ] DB/Redis/Broker private。
- [ ] RDS/等价DB HA+PITR。
- [ ] Secrets最小权限。
- [ ] Staging image promote到Production。
- [ ] Canary/rollback实测。
- [ ] Alerts/backups/security gate ready。
- [ ] 外部账号依赖明确完成或对应功能关闭。

## 21. Definition of Done

```text
production infrastructure provisioned
+ RC deployed via CI/CD
+ canary successful
+ smoke/SLO green
+ rollback path verified
```

下一节点：NODE-73 Final Acceptance。
