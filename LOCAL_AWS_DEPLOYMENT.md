# LUMI AI Design OS — LOCAL AWS DEPLOYMENT

> **Document:** `LOCAL_AWS_DEPLOYMENT.md`
> **Mode:** Codex Local Full-Automation / AWS
> **Repository:** `zhangjaky71-stack/LUMI-AI-DESIGN-OS`
> **Primary user command:** `按照文档继续部署`
> **Default AWS Region:** `ap-northeast-1`（除非仓库/现有 AWS 配置已经明确指定其他 Region）
> **Primary target:** Staging-first, Production-ready
> **IaC:** Terraform
> **Compute:** Amazon ECS on AWS Fargate
> **Data:** Amazon RDS for PostgreSQL + ElastiCache + S3
> **Images:** Amazon ECR
> **Secrets:** AWS Secrets Manager
> **Ingress:** Application Load Balancer
> **Observability:** CloudWatch Logs / Metrics / Container Insights
> **Principle:** 不要求非工程用户手工填写 Terraform / IAM / VPC / Security Group / Account ID / AZ / ARN / ECR / S3 参数。

---

# 0. Codex 必须如何理解“按照文档继续部署”

当用户在 Codex 客户端只输入：

```text
按照文档继续部署
```

Codex 必须把它解释为：

> 读取本文件和当前仓库，检查上一次部署进度，自动完成当前可执行的下一阶段；自行检查本机工具、AWS 登录状态、仓库代码、Docker 构建入口、服务依赖、Terraform 状态和 AWS 现有资源；能通过仓库、AWS API、Terraform、AWS CLI、Git、Docker、PowerShell 自动发现或生成的参数全部自动处理。不要让用户手工输入 Terraform variables、Account ID、VPC/Subnet/AZ、IAM ARN/Policy、Security Group、ECR、S3 bucket、RDS/Redis 地址、数据库密码等参数。只有浏览器登录/MFA、AWS 权限不足、付费/实名、生产域名所有权、第三方生产 API Secret 等真正无法代替用户完成的外部动作才允许中断。

Codex 不得因为“缺少一个参数”直接询问用户。必须先依次尝试：

1. 从仓库配置和 `.env*` / config / package / pyproject / compose / existing IaC 自动解析。
2. 从本机环境变量、AWS profile、AWS CLI config、Git config 自动解析。
3. 通过 AWS API 自动发现。
4. 使用本文件定义的安全默认值自动生成。
5. 对 Secret 使用密码学安全随机值，并直接保存到 AWS Secrets Manager。
6. 只有前五种方法都无法安全解决时，才把问题缩小成一个不可替代的用户动作。

---

# 1. 最终目标

本路线不是“教用户怎么部署”，而是让 **Codex 直接完成部署**。

最终应达到：

```text
Windows 11 + Codex Desktop
          │
          │ 用户只说：按照文档继续部署
          ▼
Repository inspection
          ↓
Local preflight / dependency repair
          ↓
AWS browser/SSO temporary login
          ↓
Terraform backend bootstrap
          ↓
Terraform generate / validate / plan
          ↓
AWS network + IAM + ECR + S3 + DB + Cache
          ↓
Docker build
          ↓
ECR push by immutable git-SHA tag
          ↓
ECS Fargate deploy
          ↓
Database migration
          ↓
Health / smoke / integration checks
          ↓
CloudWatch / alarms / backups
          ↓
Deployment report + Git commit
          ↓
Staging accepted
          ↓
Production promotion when prerequisites are satisfied
```

这个文档同时是部署 **Runbook、Codex 执行协议和验收标准**。

---

# 2. 本项目 AWS 架构冻结

除非后续架构 ADR 明确推翻，本项目 AWS 首选架构固定为：

```text
Internet
   │
   ▼
Application Load Balancer
   │
   ├──────── web / admin
   │
   └──────── api
               │
               ▼
      Private ECS Fargate Subnets
               │
     ┌─────────┼───────────────┐
     │         │               │
     ▼         ▼               ▼
 API/Web   Agent Runtime   Media/Other Workers
     │         │               │
     └─────────┼───────────────┘
               │
       ┌───────┼─────────────────────────┐
       ▼       ▼                         ▼
  RDS PostgreSQL     ElastiCache      S3 Buckets
  + required ext.     Redis-compatible assets/exports/sandbox
       │
       └── Optional Amazon MQ for RabbitMQ
           ONLY when code inspection proves AMQP/RabbitMQ is required
```

同时使用：

- Amazon ECR：容器镜像。
- AWS Secrets Manager：数据库和应用 Secret。
- AWS CloudWatch：日志、指标、告警。
- IAM Task Role / Execution Role：最小权限。
- Route 53 + ACM：仅在自动检测到可用域名/Hosted Zone 时自动配置。
- Terraform S3 remote state：S3 原生 lockfile，不新建 DynamoDB 锁表。

## 2.1 为什么不默认使用 EKS

本项目首期是 Modular Monolith + Specialized Workers，生产并不要求 Kubernetes。Codex 不得为了“看起来更云原生”擅自引入 EKS、Helm、ArgoCD、Service Mesh 等额外复杂度。

只有后续出现明确的以下需求，才允许通过 ADR 升级到 EKS：

- 大规模独立服务伸缩。
- GPU/Kubernetes workload 约束。
- 复杂多集群治理。
- ECS 已无法满足的调度能力。
- 已经有成熟 K8s/SRE 运维体系。

---

# 3. Codex 操作权限和安全边界

## 3.1 Codex 可以自动执行

在用户说“按照文档继续部署”后，Codex可直接执行非破坏性和可回滚操作，包括：

- 读取仓库。
- 创建/修改部署文档、Terraform、Dockerfile、PowerShell 脚本、GitHub Actions。
- 安装缺失的普通开发工具（若 Windows UAC 弹窗出现，只要求用户批准系统弹窗）。
- 运行 lint / test / build。
- 创建 staging AWS 基础设施。
- 创建 IAM Role/Policy。
- 创建 ECR/S3/RDS/ElastiCache/ECS/ALB/CloudWatch 等 staging 资源。
- 生成并存储 Secret。
- 构建并推送镜像。
- 执行 staging DB migration。
- 发布 staging。
- 执行 smoke / health / regression。
- 对失败的无状态 ECS 发布自动回滚。
- 生成部署报告。
- 在测试通过后提交部署代码到 Git。

## 3.2 Codex 不得自动做

以下操作必须停止并说明原因，而不是自行冒险：

- 删除或清空生产数据库。
- 删除生产 S3 bucket 或对象。
- 销毁 production Terraform state。
- 对生产 RDS 做无备份的 destructive replacement。
- 把数据库、Redis、RabbitMQ、内部服务暴露到公网。
- 把 Secret 写入 Git、Markdown、Terraform `.tfvars`、日志、commit message。
- 创建长期 IAM Access Key 作为默认认证方式。
- 使用 root access key。
- 绕过 MFA / Organizations SCP / IAM permission boundary。
- 在未知影响下执行 `terraform apply`，且 plan 含生产 stateful resource destroy/replacement。
- 自动购买域名、升级付费第三方 API 套餐或执行企业实名认证。

## 3.3 Destructive plan guard

每次 Terraform apply 前必须解析 plan。

如果出现：

```text
destroy
replace
-/+
```

Codex 必须分类：

- **无状态 staging 资源**：确认可重建后可自动继续。
- **有状态 staging 资源**：先做 snapshot/backup，再继续。
- **任何 production RDS/S3/MQ/关键 state**：不得静默继续；先生成风险摘要，要求一次明确确认。

正常的 production rolling ECS update、不破坏数据库的扩容/参数更新、镜像更新不要求用户逐项确认。

---

# 4. 本机环境自动检查

Codex 每次进入本文件时先运行 preflight，不依赖用户回忆已安装什么。

最低检查：

```powershell
git --version
docker version
aws --version
terraform version
node --version
corepack --version
pnpm --version
python --version
uv --version
```

然后读取：

```text
.node-version
.python-version
package.json
pnpm-lock.yaml
pyproject.toml
uv.lock
Makefile
infra/compose/*
apps/*
services/*
docs/00-MASTER-IMPLEMENTATION-PLAN.md
docs/01-ARCHITECTURE-V2-FREEZE.md
```

## 4.1 Node 版本规则

仓库 `.node-version` / `package.json` 是唯一准则。

如果 Windows 当前 Node 比仓库要求的新，例如系统装了 Node 25 而仓库要求 Node 24：

- 不修改仓库 engine 来迁就本机。
- 优先用版本管理器安装隔离的 Node 24。
- 或在 Docker 构建阶段使用仓库指定 Node 版本。
- 不要求用户卸载系统 Node。
- Codex自己完成版本切换或构建隔离。

## 4.2 Python 规则

遵循根 `pyproject.toml` / `.python-version`。

若项目固定 Python 3.12：

- 使用 `uv` 创建/同步环境。
- 不要求用户手工创建 venv。
- 不修改 Python baseline 只为解决本机环境问题。

## 4.3 缺失工具

优先通过 Windows `winget` 或项目认可的 package manager 自动安装：

- AWS CLI v2。
- Terraform current stable。
- Git（若缺）。
- Docker Desktop（若缺，但首次启动/许可可能需要用户点一次 UI）。
- `uv`。
- Node version manager（需要时）。

安装后必须重新验证版本。

---

# 5. AWS 登录：不要让用户创建 Access Key

先执行：

```powershell
aws sts get-caller-identity
```

若成功，直接复用当前临时/已配置身份。

若失败：

1. 枚举现有 AWS profiles。
2. 如果 profile 是 IAM Identity Center/SSO，执行：

```powershell
aws sso login --profile <auto-detected-profile>
```

3. 如果没有 SSO profile，且 AWS CLI >= 2.32，优先使用浏览器登录：

```powershell
aws login --profile lumi-deploy --region ap-northeast-1
```

4. 浏览器弹出时，用户只负责登录/MFA/授权；Codex继续后续步骤。
5. 登录后再次运行 `aws sts get-caller-identity`。

禁止要求用户把以下内容贴进 Codex：

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN
```

只有用户所在组织已经明确规定某种现有凭证方式时才遵循组织方式。

---

# 6. AWS 参数全部自动发现

成功登录后，Codex自动获取：

```powershell
aws sts get-caller-identity
aws configure get region
aws ec2 describe-availability-zones
```

生成本次 deployment context：

```json
{
  "account_id": "from-sts",
  "region": "existing-or-ap-northeast-1",
  "environment": "staging",
  "project": "lumi-ai-design-os",
  "git_sha": "current-git-sha",
  "available_azs": ["auto", "auto"]
}
```

## 6.1 自动命名规则

不得问用户“bucket 叫什么”“cluster 叫什么”“role 叫什么”。

统一用：

```text
lumi-<env>-<component>
```

全局唯一资源追加自动发现值：

```text
lumi-<env>-<component>-<account_id>-<region>
```

示例只是模式，不要求用户填：

```text
lumi-staging-ecs
lumi-staging-api
lumi-staging-web
lumi-staging-assets-<account>-ap-northeast-1
lumi-staging-tfstate-<account>-ap-northeast-1
```

AWS Account ID 必须由 STS 自动发现。

## 6.2 Region 决策

Region 优先级：

1. `LUMI_AWS_REGION` 环境变量（若已有）。
2. 项目已有 Terraform/AWS deployment config。
3. 当前有效 AWS profile 的 region。
4. 默认 `ap-northeast-1`。

不要问用户 Region，除非现有资源跨 Region 冲突且自动判断会造成数据迁移。

## 6.3 Availability Zone

使用 AWS API选择当前 Region 可用 AZ。

默认使用两个 AZ。

绝不让用户手填 `ap-northeast-1a` / `1c` 等值。

---

# 7. Terraform 文件布局

如果 `infra/terraform` 还没有实施内容，Codex创建：

```text
infra/terraform/
├── README.md
├── versions.tf
├── modules/
│   ├── network/
│   ├── iam/
│   ├── ecr/
│   ├── s3/
│   ├── rds/
│   ├── redis/
│   ├── mq/
│   ├── ecs-cluster/
│   ├── ecs-service/
│   ├── alb/
│   ├── dns/
│   └── observability/
└── envs/
    ├── staging/
    │   ├── backend.tf
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── locals.tf
    │   ├── outputs.tf
    │   └── terraform.tfvars.example
    └── production/
        ├── backend.tf
        ├── main.tf
        ├── variables.tf
        ├── locals.tf
        ├── outputs.tf
        └── terraform.tfvars.example
```

另外创建：

```text
scripts/aws/
├── preflight.ps1
├── auth.ps1
├── bootstrap-state.ps1
├── plan.ps1
├── apply.ps1
├── build-push.ps1
├── migrate.ps1
├── deploy.ps1
├── smoke-test.ps1
├── status.ps1
├── rollback.ps1
└── destroy-staging.ps1
```

这些脚本是给 Codex 调用的，不是让用户照着输入。

---

# 8. Terraform remote state 自动 bootstrap

Terraform state 不允许只留在个人电脑。

Codex在 `terraform init` 之前用 AWS CLI 幂等创建 state bucket：

```text
lumi-terraform-state-<account_id>-<region>
```

必须开启：

- S3 Block Public Access 全部选项。
- Bucket versioning。
- Server-side encryption。
- 明确的 least-privilege bucket policy。
- 独立 state key：
  - `staging/terraform.tfstate`
  - `production/terraform.tfstate`

Terraform S3 backend 开启：

```hcl
use_lockfile = true
```

不要新建 DynamoDB Terraform lock table；S3 backend 的 DynamoDB locking 已是 deprecated 路线。

Credentials 不写入 `backend.tf`，使用 AWS profile / temporary credentials / standard credential chain。

---

# 9. VPC / 网络：Codex 自动生成

## 9.1 默认 CIDR

如果账号内不存在冲突 VPC，默认：

```text
VPC: 10.42.0.0/16
```

Codex先读取账号现有 VPC CIDR。

若冲突，自动选择下一个不冲突的 RFC1918 CIDR，不询问用户。

## 9.2 两个 AZ

每个环境至少：

```text
2 x public subnets
2 x private app subnets
2 x private data subnets
```

## 9.3 路由

Public：

- ALB。
- NAT Gateway（按环境 profile）。

Private app：

- ECS Fargate。
- 可访问 RDS / Redis / MQ。
- 需要对外调用 OpenAI、模型厂商、搜索 API 等，因此允许受控 outbound。

Private data：

- RDS。
- ElastiCache。
- Optional Amazon MQ。
- 不分配 public IP。

## 9.4 NAT 默认策略

Staging：

```text
1 NAT Gateway
```

优先成本控制。

Production：

```text
2 NAT Gateways / one per AZ
```

优先高可用。

若后续通过 VPC Endpoints 可减少 NAT traffic，Codex可以增加：

- S3 Gateway Endpoint。
- ECR API / DKR Interface Endpoints。
- Secrets Manager Endpoint。
- CloudWatch Logs Endpoint。

但不能因为加了 endpoints 就错误删除模型 Provider 需要的公网 outbound。

---

# 10. Security Group 规则

Codex自动创建 Security Groups，不让用户填写端口表。

## 10.1 ALB SG

Internet inbound：

```text
80  -> redirect to HTTPS when certificate exists
443 -> ALB
```

无域名/certificate 的首轮 staging 可临时用 HTTP ALB DNS 做验收，但必须在报告中标记：

```text
TLS_DOMAIN_PENDING
```

## 10.2 ECS SG

Inbound：

- 仅来自 ALB SG 的公开 Web/API 端口。
- 内部 service-to-service 端口仅来自 ECS/internal SG。

Outbound：

- RDS / Redis / MQ / AWS endpoints。
- 需要的第三方 AI Provider HTTPS。

## 10.3 RDS SG

只允许 ECS/migration SG 到 PostgreSQL port。

禁止：

```text
0.0.0.0/0 -> 5432
```

## 10.4 Redis SG

只允许 ECS SG。

禁止公网访问。

## 10.5 MQ SG

仅当使用 Amazon MQ：

- 只允许使用 RabbitMQ 的 ECS services。
- 管理界面不得暴露公网。

---

# 11. S3 Object Storage

本地 MinIO 在 AWS 上默认映射为原生 S3。

自动创建环境隔离 buckets 或严格隔离 prefixes，优先 buckets：

```text
lumi-<env>-assets-<account>-<region>
lumi-<env>-exports-<account>-<region>
lumi-<env>-sandbox-<account>-<region>
```

必须：

- Block Public Access。
- Server-side encryption。
- Versioning：assets/exports 开启；sandbox 可按生命周期策略清理。
- Lifecycle rules。
- CORS 最小化。
- 使用 presigned URL。
- Bucket Policy 限定 task roles。
- 不允许应用持有全账号 S3 权限。

任何用户文件都不能默认 `public-read`。

---

# 12. PostgreSQL / pgvector

本地当前使用 PostgreSQL 17 + pgvector 方向，AWS 默认使用 **RDS for PostgreSQL 17 的当前可用稳定 minor**，但 Codex必须先用 AWS API检查目标 Region 实际支持版本，不能把过时 minor 写死。

## 12.1 Staging

默认成本优先：

- 单实例。
- 非公网。
- encrypted storage。
- automated backup。
- deletion protection 可按 staging 策略关闭，但 Terraform destroy guard 保留。

## 12.2 Production

默认：

- Multi-AZ。
- storage encryption。
- deletion protection。
- automated backups。
- 合理 retention。
- Performance Insights/Database Insights 能启用则启用。
- 升级必须先 snapshot。

## 12.3 数据库密码

RDS master password：

```text
manage_master_user_password = true
```

让 RDS / Secrets Manager 生成并管理。

不要把 master password 放入 Terraform `.tfvars`。

应用数据库用户和 migration 用户：

- 首次 migration/bootstrap 任务自动创建。
- 密码使用 secure random。
- 直接写 Secrets Manager。
- 不输出明文。
- Task Definition 仅引用 Secret ARN。

## 12.4 pgvector

在正式 migration 前：

```sql
SHOW rds.extensions;
```

确认 `vector` 可用。

然后根据 migration idempotently 执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

如果目标 RDS 版本不支持项目要求的 extension/version：

- 停止数据库 migration。
- 自动尝试兼容的 RDS PostgreSQL minor/major 组合。
- 不允许在未知兼容性下强行上线。

---

# 13. Redis / ElastiCache

Codex先扫描代码实际使用：

- Redis cache。
- rate limit。
- locks。
- queue/stream。
- pub/sub。
- persistence assumptions。
- Lua / Redis feature dependencies。

默认优先选择当前 AWS 支持的 ElastiCache Redis-compatible 方案。

如果应用能力与 Serverless兼容：

```text
ElastiCache Serverless
```

否则自动使用 provisioned replication group。

必须：

- private subnets。
- encryption in transit。
- encryption at rest（适用时）。
- security group 限制。
- 应用连接信息以 config/secret 注入。
- 不在 Git 里保存 Redis password/token。

---

# 14. RabbitMQ：按代码决定，不按 Compose 盲目部署

本地 Compose 当前存在 RabbitMQ，但这不代表 AWS production 必须创建 MQ。

Codex必须先扫描真实代码：

```text
amqp
rabbitmq
aio-pika
pika
kombu
celery broker
RabbitMQ queue/exchange
```

## 14.1 没有实际使用

不要创建 Amazon MQ。

这样避免无意义持续费用和维护面。

## 14.2 实际使用 RabbitMQ

优先考虑 Amazon MQ for RabbitMQ，但部署前必须验证：

- 当前代码的 queue type。
- 是否依赖 classic queue 特定语义。
- 是否使用 RabbitMQ Streams。
- client compatibility。
- 当前 AWS 支持的 engine version。

Amazon MQ RabbitMQ 4.x 的行为和本地 RabbitMQ 4.x 必须做 integration test。

如果代码使用 Amazon MQ 不支持的 RabbitMQ Streams：

- 不得强行改成 Amazon MQ。
- 创建部署阻塞项和迁移 ADR。
- 选择自管 RabbitMQ on ECS/EC2 或重构到兼容消息层后再继续。

---

# 15. ECR 与 Docker

Codex扫描所有 deployable components，不能仅凭文件夹名全部发布。

当前候选包括但不限于：

```text
apps/web
apps/admin
apps/api
apps/agent-runtime
apps/worker-media
services/model-gateway
services/tool-gateway
services/sandbox-runtime
services/memory
services/knowledge
services/visual-critic
services/asset-intelligence
```

对每个候选，检查：

- 是否有真正可运行 entrypoint。
- 是否有 HTTP server / worker command。
- exposed port。
- health endpoint。
- runtime dependencies。
- 是否已经被另一个 modular monolith 包含。
- 是否需要独立伸缩/安全边界。

生成 `deployable-service-matrix`，避免空壳服务也创建 ECS service。

## 15.1 Dockerfile 不存在时

Codex自动生成 production Dockerfile：

- multi-stage build。
- 版本遵循 repo lockfiles。
- Python 使用项目固定版本。
- Node 使用 `.node-version`。
- 非 root user。
- 最小 runtime image。
- 不复制 `.env` / secrets。
- reproducible install。
- build cache 合理。
- HEALTHCHECK 或 ECS health endpoint。
- 优先 `linux/amd64`，若依赖确认支持 arm64 且成本/性能合适可通过 ADR 调整。

## 15.2 Image tag

禁止只用 `latest` 作为可追踪发布。

必须推送 immutable tag：

```text
<git-sha>
```

可额外维护：

```text
staging
production
```

但 ECS Task Definition 必须能够定位到 immutable digest/tag。

Production promotion 使用 **staging 已验证的同一 image digest**，不要重新 build 一份“看起来一样”的镜像。

---

# 16. IAM：Codex生成，不让用户写 JSON Policy

IAM 分离：

```text
deployment role / current caller
ECS task execution role
per-service ECS task role
migration task role
```

## 16.1 Execution Role

只给：

- ECR image pull。
- CloudWatch log delivery。
- ECS读取指定 Secrets Manager values 所需权限。

## 16.2 Task Role

每个服务按实际依赖单独生成：

例如 API：

- 指定 S3 buckets/prefixes。
- 指定 Secrets Manager ARNs。
- 必要 AWS service calls。

Worker：

- 指定 assets/exports/sandbox buckets。
- 必要 queue/cache/secrets。

不允许给所有 ECS task 一个统一 `AdministratorAccess`。

## 16.3 Wildcard policy

`Resource = "*"` 只有在 AWS API 本身不支持 resource-level restriction 或确有技术要求时才允许。

Codex必须在 deployment report 记录每个 wildcard 的理由。

---

# 17. Secrets Manager

Secret naming：

```text
/lumi/<env>/<service>/<name>
```

例如：

```text
/lumi/staging/api/database-url
/lumi/staging/api/session-secret
/lumi/staging/model-gateway/openai-api-key
```

## 17.1 自动生成 Secret

内部 Secret 自动用 cryptographically secure RNG 生成，例如：

- app signing secret。
- internal service token。
- DB application password。
- migration password。

生成后直接写 Secrets Manager，不打印明文。

## 17.2 第三方 Provider Secret

Codex先检查：

- process environment。
- 本机未提交的 `.env`。
- 已存在 Secrets Manager。
- 项目已支持的 Secret provider。

如果已经存在，安全迁移/引用，不回显。

如果缺少可选 Provider API key：

- 不阻塞 AWS 基础设施部署。
- 标记 provider `DISABLED_MISSING_SECRET`。
- 继续完成可完成的 smoke tests。

如果缺少上线必须的第三方 production key：

- 不让用户把 key 粘贴进聊天。
- 只提示用户把该值放到指定的本机环境变量，或在 AWS Secrets Manager UI 中输入一次。
- 用户完成后，下一句仍然只需要：
  `按照文档继续部署`

---

# 18. ECS Cluster / Service

创建：

```text
lumi-staging
lumi-production
```

ECS Fargate。

对 HTTP services：

- ALB Target Group。
- `/healthz` 和 `/readyz`（仓库没有就补）。
- deployment circuit breaker。
- automatic rollback。
- CloudWatch Logs。
- sensible stop timeout / graceful shutdown。
- task CPU/memory 根据代码和 staging smoke 初值自动配置。

对 Worker：

- 不挂公网 ALB。
- 通过 queue/job机制工作。
- 独立 autoscaling policy（当实际 metrics 可用）。

## 18.1 Staging desired count

默认节省成本：

- internet-facing web/API：1。
- agent/worker：按功能最低可运行数。
- 未实现/空壳服务：0 / 不创建。

## 18.2 Production desired count

对关键 HTTP 服务默认至少 2 tasks，跨 AZ。

Workers根据 workload/queue metrics 扩缩。

---

# 19. ALB 路由

Codex通过代码和现有 frontend config 自动决定实际路由。

推荐目标：

```text
/            -> web
/api/*       -> api
```

如果 Next.js 已经统一 proxy 到 API，保留项目真实 contract，不强制改 URL。

Admin：

- 若是同一前端 bundle，按代码运行。
- 若是独立 app，可用 `admin.<domain>` 或 internal path。
- 生产 admin 必须受 Auth/RBAC 保护。

ALB health check 必须命中真实 ready endpoint，不允许仅 TCP 活着就判 healthy。

---

# 20. 域名 / TLS

Codex先自动检查：

```text
Route 53 Hosted Zones
ACM certificates
existing domain env/config
```

如果存在可用 Hosted Zone 且权限足够：

- 自动申请/验证 ACM certificate。
- 自动创建 DNS records。
- ALB 80 redirect 443。
- 输出 URL。

如果没有域名：

- staging 不被阻塞。
- 使用 ALB DNS 完成基础验收。
- 标记 `TLS_DOMAIN_PENDING`。
- production promotion 到公共正式入口前，才要求用户完成域名拥有权/购买这一不可代步骤。

Codex不得自动替用户购买域名。

---

# 21. Database migration

部署次序：

```text
RDS ready
  ↓
Secrets ready
  ↓
Migration task definition
  ↓
One-off ECS migration task
  ↓
Migration success
  ↓
Application service rollout
```

Migration：

- 使用独立 migration role / DB user。
- migration container 与 app release 同 git SHA。
- idempotent。
- 输出 schema revision，但不输出 credentials。
- production migration 前自动 RDS snapshot。
- destructive migration 必须被 CI/check识别并阻止静默发布。

如果 migration 失败：

- 不发布新应用版本。
- 保持旧版本在线。
- 保存 logs。
- 修复后继续。

---

# 22. CloudWatch / Observability

必须至少配置：

- ECS service/task logs。
- API/Web error logs。
- RDS metrics。
- ElastiCache metrics。
- ALB 4xx/5xx / target response time。
- ECS CPU/memory。
- Container Insights（优先 enhanced observability，若账号权限/成本策略允许）。
- deployment failure events。

推荐 alarms：

```text
ALB 5xx elevated
Unhealthy target > 0
ECS running task below desired
RDS CPU/storage/connections pressure
Redis errors/evictions/connection pressure
```

LangSmith 继续承担 AI trace/eval；CloudWatch 不替代 LangSmith。

不要把 prompt 中的敏感用户素材或 provider key原样写 CloudWatch。

---

# 23. Backup / Recovery

Staging：

- RDS automated backups。
- S3 versioning。
- Terraform state bucket versioning。

Production：

- RDS Multi-AZ。
- automated backups。
- pre-migration snapshot。
- deletion protection。
- S3 versioning/lifecycle。
- Terraform state versioning。
- 恢复 Runbook。

Codex必须生成：

```text
docs/runbooks/AWS-ROLLBACK.md
docs/runbooks/AWS-RECOVERY.md
```

如果已经存在则更新，不重复创建平行 runbook。

---

# 24. Terraform plan / apply 流程

每次：

```powershell
terraform fmt -recursive
terraform init
terraform validate
terraform plan -out=<planfile>
```

然后机器检查 plan。

Staging安全 plan：

```powershell
terraform apply <planfile>
```

不要让用户复制：

```text
yes
var.account_id
var.vpc_id
var.subnet_ids
var.role_arn
...
```

这些值必须自动生成/发现。

## 24.1 不保存 secret tfvars

`terraform.tfvars.example` 只能包含非 Secret example/default。

真实 Secret 不写：

```text
*.tfvars
.env committed
outputs
reports
```

---

# 25. Staging 部署状态机

Codex使用以下状态推进，不要每一步都问用户“下一步吗”。

```text
S00 REPO_INSPECTED
S01 LOCAL_PREFLIGHT_OK
S02 AWS_AUTH_OK
S03 TF_BACKEND_OK
S04 TF_VALIDATE_OK
S05 NETWORK_READY
S06 DATA_READY
S07 ECR_READY
S08 IMAGES_PUSHED
S09 SECRETS_READY
S10 MIGRATION_OK
S11 ECS_READY
S12 STAGING_HEALTH_OK
S13 STAGING_SMOKE_OK
S14 OBSERVABILITY_OK
S15 REPORT_WRITTEN
S16 GIT_COMMITTED
S17 STAGING_ACCEPTED
```

当一次 Codex 会话因为浏览器登录、UAC、AWS异步资源等待之外的真正阻塞而中断，下次用户仍只说：

```text
按照文档继续部署
```

Codex必须从实际 AWS/Terraform/Git 状态重新发现，并从正确节点继续，不能假定从零开始，也不能重复创建资源。

---

# 26. 本地 deployment checkpoint

可以创建：

```text
.local/aws-deployment-state.json
```

或项目已有等价目录。

它只能保存非 Secret metadata：

```json
{
  "environment": "staging",
  "region": "ap-northeast-1",
  "last_stage": "S11_ECS_READY",
  "last_git_sha": "...",
  "last_plan_sha256": "...",
  "updated_at": "..."
}
```

必须加入 `.gitignore`。

但 checkpoint 不是唯一真相源。

真实状态优先级：

1. AWS API。
2. Terraform remote state。
3. Git。
4. Local checkpoint。

---

# 27. Smoke / Acceptance

至少自动执行：

```text
ALB responds
web health
api health
api readiness
database connection
Redis connection
S3 write/read/delete test on dedicated smoke prefix
agent runtime health
worker startup
Model Gateway health
Tool Gateway health
one minimal end-to-end request when provider secret exists
```

同时运行仓库现有：

```text
format
lint
typecheck
unit tests
integration tests
build
e2e/smoke where feasible
agent eval smoke where feasible
```

失败时：

- 自动收集相关 ECS events / task exit reason / logs。
- 修复代码/infra。
- 重新 build/push。
- 重新 deploy。
- 不把一屏 AWS 错误直接甩给非工程用户让他自己排查。

---

# 28. Production promotion

只有 staging `S17_STAGING_ACCEPTED` 后才进入 production。

Production必须重新检查：

```text
P00 production prerequisites
P01 terraform plan
P02 backup/snapshot
P03 production infra ready
P04 secrets ready
P05 migration ready
P06 same validated image digest
P07 rolling deploy
P08 health
P09 smoke
P10 alarms
P11 final report
```

Production和 staging：

- 不共享数据库。
- 不共享 mutable object prefix。
- 不共享第三方生产 Secret。
- 不共享 OAuth callback。
- 不共享 LangSmith project。
- Terraform state key分离。

如果正式域名、production API key、支付账户等还没准备好，Codex可以把 production infrastructure推进到安全可行阶段，并明确列出唯一阻塞项；不要要求用户重新填写已有参数。

---

# 29. Git 策略

每次部署自动化代码变更前：

```powershell
git status --short --branch
```

规则：

- 不 `git reset --hard` 用户已有工作。
- 不覆盖未提交用户修改。
- 若工作区有无关变更，隔离自己的文件或创建专用 branch。
- infrastructure/doc脚本测试通过后 commit。
- 不 commit `.terraform/`、plan binary、state、credentials、`.env`、Secret。
- commit message 清晰，例如：

```text
docs(deploy): add Codex local AWS deployment runbook
feat(infra): add AWS ECS Terraform baseline
chore(deploy): add ECR build and smoke automation
```

如果项目 policy要求 PR，则创建 branch/PR；否则按当前仓库既定协议提交。

---

# 30. 每次完成后必须生成报告

写入：

```text
reports/deployment/aws-<env>-latest.md
```

报告只含非 Secret 信息：

```text
Environment
Region
Git SHA
Terraform plan summary
Created/updated resources
ECS services
Image digests
ALB URL / domain
Health result
Smoke result
Migration revision
CloudWatch log groups
Known warnings
Missing external secrets
Pending domain/TLS
Rollback target
Next automatic step
```

AWS Account ID如无必要只显示末4位或 hash。

绝不写：

- passwords。
- API keys。
- session tokens。
- secret payload。
- database connection string with password。

---

# 31. 允许打断用户的唯一情况

Codex只有以下情况可以要求用户介入：

| 类别 | 用户需要做什么 | Codex不得要求什么 |
|---|---|---|
| AWS browser login / MFA | 在浏览器完成登录/验证码 | 不得要 Access Key |
| Windows UAC | 点系统允许 | 不得让用户手工装一堆包 |
| IAM/SCP 权限不足 | 请 AWS 管理员授予缺少的明确 permission | 不得让用户写 IAM JSON |
| AWS Billing/实名 | 在 AWS 完成账号级要求 | 不得绕过 |
| 域名购买/所有权 | 用户购买或确认域名所有权 | 不得擅自购买 |
| 第三方生产 Secret | 用户在指定安全位置录入一次 | 不得让用户贴到聊天/Git |
| 生产 destructive change | 用户确认风险摘要 | 不得要求用户读 Terraform raw plan |

发生阻塞时提示应非常短：

```text
现在只需要你完成 1 件事：浏览器里的 AWS 登录/MFA。
完成后回到 Codex，仍然只输入：按照文档继续部署
```

不要把内部 Terraform/IAM 参数转嫁给用户。

---

# 32. 成本控制原则

Codex不是只追求“最豪华架构”。

Staging 默认：

- ECS Fargate 小规格起步。
- desired count最低可用。
- 1 NAT Gateway。
- RDS非Multi-AZ。
- 能用Serverless且兼容时优先Serverless cache。
- RabbitMQ没有真实使用就不建 Amazon MQ。
- CloudWatch retention设置合理期限。
- S3 lifecycle清理临时 sandbox/export。
- 不创建 EKS。
- 不创建 OpenSearch / MSK 等未证明需要的高固定成本服务。

Production再打开：

- 2 NAT。
- Multi-AZ RDS。
- 多 task。
- 更强备份/保护。
- 实际负载驱动 autoscaling。

任何新增高固定成本 AWS 服务必须能解释为什么当前 LUMI 代码确实需要。

---

# 33. Failure self-repair playbook

## 33.1 Docker build失败

Codex：

1. 读取 build error。
2. 核对 lockfile/runtime version。
3. 修 Dockerfile。
4. 本地重建。
5. 测 health。
6. 重新push。

不要求用户复制错误到 ChatGPT。

## 33.2 ECS task起不来

自动检查：

```text
ECS service events
stopped task reason
container exit code
CloudWatch logs
secret permission
ECR pull permission
security group
health check
CPU/memory
command/entrypoint
```

修复后发布新 task definition。

## 33.3 DB连接失败

自动检查：

```text
RDS status
SG
DNS
secret ARN
SSL settings
user/database
migration state
```

不临时开放 RDS 公网来“测试一下”。

## 33.4 Terraform state lock

确认没有活跃 apply 后再处理 stale lock。

不得删除正常正在运行的 lock。

## 33.5 Failed ECS deployment

启用 deployment circuit breaker + rollback，保持最近 healthy revision。

---

# 34. Codex 第一次执行时的具体任务

用户第一次输入“按照文档继续部署”时，Codex必须直接开始：

```text
A. git status / repo inspection
B. read architecture + compose + app/service entrypoints
C. preflight local tools
D. establish AWS temporary auth
E. discover account/region/AZ/current resources
F. generate Terraform skeleton if missing
G. bootstrap S3 Terraform backend
H. generate staging Terraform
I. terraform fmt/validate/plan
J. apply safe staging infrastructure
K. generate production Dockerfiles where missing
L. build/test images
M. push ECR with git SHA
N. create/import secrets
O. run DB bootstrap/migration
P. create/update ECS services
Q. run health/smoke/eval
R. configure logs/alarms
S. write deployment report
T. commit deployment automation
```

Codex应连续执行，直到：

- staging成功；或
- 遇到第31节定义的真正外部阻塞。

不要在 A、B、C、D 之间逐步询问“是否继续”。

---

# 35. Codex 后续执行时的具体任务

再次看到：

```text
按照文档继续部署
```

不要重复整套脚本。

先运行：

```text
git status
terraform state / terraform plan
aws sts get-caller-identity
aws ecs describe-services
aws rds describe-db-instances
aws elasticache ...
aws s3api ...
```

恢复实际状态。

随后：

- 修复 unfinished stage。
- 若 staging未通过，继续 staging。
- 若 staging已通过且 production prerequisites未齐，补齐可自动完成部分。
- 若 production已具备条件，按 production promotion state machine继续。
- 若全部已完成，则改为执行 drift/health检查并报告“无需变更”。

这使“按照文档继续部署”同时具备 **resume + repair + deploy + verify** 语义。

---

# 36. Definition of Done

AWS部署节点只有同时满足下面条件才算完成：

```text
[ ] Local preflight reproducible
[ ] Temporary AWS auth path works
[ ] Terraform remote state + locking works
[ ] Terraform validate passes
[ ] Staging infra managed by Terraform
[ ] No public DB/cache/MQ
[ ] S3 public access blocked
[ ] Secrets are not in Git/state outputs/logs where avoidable
[ ] ECR images use git-SHA immutable version
[ ] ECS services healthy
[ ] DB migrations successful
[ ] pgvector requirement verified
[ ] Redis path verified
[ ] RabbitMQ decision based on code, not compose only
[ ] Deployment rollback enabled
[ ] CloudWatch logs/metrics available
[ ] Smoke tests pass
[ ] Existing repository checks pass
[ ] Deployment report generated
[ ] Rollback/recovery runbook exists
[ ] No secret leaked in git diff/history
[ ] Changes committed
[ ] Staging URL available
[ ] Production blockers, if any, reduced to external-only actions
```

---

# 37. Codex 输出给用户的格式

用户是非工程背景。

成功时不要输出几十页 Terraform log。

只输出类似：

```text
AWS Staging 部署已完成。

状态：
- AWS 登录：正常
- Terraform：已应用
- 数据库：正常
- Redis：正常
- ECS：正常
- Web/API：正常
- Smoke Test：通过
- 日志/监控：已启用
- Git：已提交

访问地址：
<URL>

下一步：
如需继续 Production，仍然只输入：
按照文档继续部署
```

被外部动作阻塞时只输出一件需要用户做的事。

---

# 38. 官方依据 / 实施时重新核验

Codex在真正执行时必须重新读取 AWS/HashiCorp 官方文档，避免依赖过时静态版本信息。

重点官方资料：

- AWS CLI browser sign-in / `aws login`
  https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html

- AWS CLI IAM Identity Center / SSO
  https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html

- Terraform S3 backend / S3 lockfile
  https://developer.hashicorp.com/terraform/language/backend/s3

- Amazon ECS deployment circuit breaker
  https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DeploymentCircuitBreaker.html

- ECS + Secrets Manager
  https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html

- RDS + Secrets Manager managed master password
  https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-secrets-manager.html

- RDS PostgreSQL extensions
  https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.FeatureSupport.Extensions.html

- Amazon S3 Block Public Access
  https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html

- S3 Gateway Endpoint
  https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html

- ECR VPC endpoints
  https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html

- CloudWatch Container Insights for ECS
  https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/deploy-container-insights-ECS-cluster.html

- ElastiCache Serverless Redis-compatible cache
  https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/GettingStarted.serverless-redis.step1.html

- Amazon MQ RabbitMQ 4
  https://docs.aws.amazon.com/amazon-mq/latest/developer-guide/rabbitmq-4.html

凡是 AWS engine version、instance class、Fargate platform behavior、Terraform/AWS provider version等可能变化的内容，都应在实际部署当天用官方 API/文档重新验证，而不是硬编码本文件写作时的版本号。

---

# 39. 最终执行口令

从现在开始，用户无需说：

```text
terraform init
terraform plan
terraform apply
填 VPC
填 subnet
填 account id
创建 role
复制 policy
创建 security group
创建 ECR
```

只需要在 Codex 本地项目根目录对 Codex说：

```text
按照文档继续部署
```

Codex必须读取 `LOCAL_AWS_DEPLOYMENT.md` 并按本文件持续推进到下一个可验收状态。
