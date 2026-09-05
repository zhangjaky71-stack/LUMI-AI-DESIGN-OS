# NODE-71 — Production-like Staging Acceptance Plan

> Date: 2026-08-15  
> Status: SOURCE PLAN READY / RUNTIME EVIDENCE PENDING  
> Authority: `staging/acceptance/manifest-v1.json`

## 1. Purpose

NODE-71 is the final product-level rehearsal before production deployment. It does not accept unit-test-only evidence. A release candidate must be deployed to a production-like Staging environment and exercised across product, Agent, Canvas, media, billing, security, resilience, performance, browser, data lifecycle, observability, and recovery paths.

The machine decision is produced by `scripts/staging-acceptance-gate.py`.

## 2. Environment parity

Staging may be smaller than Production, but must use the same architecture class and release code/images. Required parity is frozen in `staging/acceptance/environment-parity-v1.json`.

At minimum record evidence for:

- exact immutable container image digests;
- topology/service-boundary parity;
- PostgreSQL engine/major;
- broker and queue semantics;
- S3-compatible object interface and authorization semantics;
- exact migration head;
- same auth/session/security code path;
- same Agent Runtime / Tool Gateway / Model Gateway build identity;
- production-class logs/metrics/traces interfaces;
- isolated Staging secrets.

Forbidden in Staging acceptance:

- real customer production data;
- local-only example credentials;
- public database/broker/MinIO/Grafana/Prometheus/Tempo/Loki/OTLP management ports;
- floating/unversioned release images;
- shared production secrets.

Current repository note: local Compose is a development baseline, not Staging IaC. `infra/terraform` is not yet a deployed production-like environment; actual cloud/deployment implementation remains a NODE-72 responsibility.

## 3. Test account matrix

Create dedicated synthetic identities only:

| Identity | Purpose |
|---|---|
| Org A Owner | full tenant administration |
| Org A Editor | normal project/design editing |
| Org A Viewer | read-only authorization checks |
| Org B Owner | cross-tenant denial matrix |
| Platform Ops | privileged platform operations |
| Billing Test Org | credits/budget/webhook tests |

Do not store passwords, tokens, or session cookies in acceptance evidence. Evidence should reference secret-manager/account fixture IDs only.

## 4. Provider modes

Use three modes deliberately:

1. **MockProvider** — high-volume E2E, deterministic failure injection, 429/5xx, latency, retries and queue tests.
2. **Provider sandbox/test mode** — integration semantics where offered.
3. **Small production-candidate quality sample** — NODE-70 quality acceptance under explicit spend budget.

If a commercial account/key is unavailable, record `BLOCKED_EXTERNAL` only for scenarios whose manifest explicitly permits an external dependency. P0 remains blocked until PASS.

## 5. Golden E2E — Brand Project

Canonical user brief:

> 为一家精品咖啡品牌完成市场研究、品牌方向、Logo/视觉体系、包装、菜单、海报、社媒素材和短视频。

Required observed chain:

```text
Project
-> Structured Brief
-> Research with sources
-> Strategy
-> Creative directions
-> Approval
-> Design/Generation
-> Canvas
-> Brand rules
-> Critic/Repair
-> Versions
-> Export
```

Evidence must identify one RC build and correlate project ID, Agent Run ID, task/graph evidence, Tool/Model traces, artifacts, Canvas version, approval, critic/repair, version history, and export artifact. Do not paste sensitive prompt bodies or credentials into the report.

## 6. Golden E2E — Precision Edit

Canonical edit instruction:

> 产品和Logo不要动，二维码位置大小不变；背景改成黑色，标题缩小15%。

Required invariants:

- title structure changes size by the requested amount/tolerance;
- background changes to black;
- product identity remains unchanged;
- Logo remains unchanged;
- QR payload is unchanged;
- QR geometry remains within frozen tolerance;
- QR remains scannable;
- a new Artifact/Design version is created;
- the old version remains restorable.

Evidence should include before/after artifact/version IDs, structured diff, constraint report, identity/brand/QR checks, and restore proof.

## 7. Resilience execution order

Run against synthetic workloads only. Each drill records start/end timestamps, RC SHA, affected service, observed user state, queue state, retries/reconciliation and recovery evidence.

Required drills:

- Agent Runtime restart during an active run;
- worker restart with queued/running work;
- provider 429 and 5xx;
- Redis restart/degradation;
- duplicate event + duplicate payment webhook + SSE reconnect;
- DB failover-equivalent or isolated restore rehearsal.

Never perform destructive recovery drills against production or an unacknowledged shared database.

## 8. Security corpus

Required P0 scenarios:

- Org A attempts Org B IDs/objects;
- unauthorized signed asset URL;
- malicious SVG/upload corpus;
- indirect prompt injection page/content;
- metadata/private-network SSRF targets;
- sandbox traversal/escape corpus;
- unauthorized Admin operation and expired approval.

A security Critical failure is STOP SHIP. `BLOCKED_EXTERNAL` is not valid for these internal security scenarios.

## 9. Billing / cost

For representative generation and repair flows verify:

- reservation before paid side effect;
- cost ledger entry created;
- budget exhaustion blocks paid work;
- test credits are not duplicated;
- duplicate webhook is idempotent;
- sample provider usage reconciles to internal cost summary.

No real charge should be generated without explicit test budget and provider authorization.

## 10. Performance

Run NODE-69 Profile G against the identified RC and environment. If Staging is smaller than launch Production capacity, report the exact scaling ratio and resource shape; never translate a smaller run into an unsupported Production claim.

Required evidence includes API/SSE/DB/Queue/Canvas/Media measurements from the same RC identity.

## 11. Browser and localization

P0:

- Chrome primary create/edit/export flow;
- Edge primary create/edit/export flow;
- Chinese IME text entry;
- production font loading/fallback;
- upload/download behavior.

P1:

- Safari core view/edit flow on available device/cloud browser. If unavailable, it may be `BLOCKED_EXTERNAL` with an evidence ticket, but it does not count as PASS.

## 12. Data lifecycle

Verify:

- Project archive/restore;
- asset deletion/retention behavior;
- vector-index deletion;
- audit record continuity;
- export expiry;
- backup restore + integrity/workload checks.

## 13. Observability

A representative E2E must be traceable across request -> Agent -> Tool/Model -> worker using bounded IDs in logs/metrics/traces. Evidence references must not contain secrets or raw sensitive payloads.

## 14. Read-only Staging preflight

Before mutation tests:

```bash
export LUMI_STAGING_HOST_ACK=staging.example.com
export LUMI_STAGING_ENV_ACK=staging
python3 scripts/staging-preflight.py \
  --base-url https://staging.example.com \
  --expected-version <exact-rc-version> \
  --output reports/staging-acceptance/<rc>/preflight.json
```

The preflight only performs GET requests to:

- `/health/live`
- `/health/ready`
- `/version`

It does not follow redirects and checks RC version plus core security headers.

## 15. Evidence record

Every scenario result uses:

```json
{
  "status": "PASS | FAIL | BLOCKED_EXTERNAL | NOT_RUN",
  "actual": "what actually happened",
  "evidence_ref": "artifact/log/trace/report reference",
  "owner": "responsible owner",
  "external_reason": "required only for BLOCKED_EXTERNAL"
}
```

A `PASS` without `actual`, `evidence_ref`, and `owner` is invalid.

## 16. Release candidate decision

Create a completed evidence file from `staging/acceptance/evidence-template.json`, then run:

```bash
python3 scripts/staging-acceptance-gate.py \
  --evidence reports/staging-acceptance/<rc>/evidence.json \
  --output reports/staging-acceptance/<rc>/decision.json \
  --markdown reports/staging-acceptance/<rc>/decision.md
```

GO-LIVE requires:

- every P0 scenario evidenced PASS;
- every required environment parity check evidenced PASS;
- no open Critical/High issue;
- engineering/security/product/release-owner approvals all APPROVED;
- synthetic-data policy satisfied;
- exact RC identity recorded.

`BLOCKED_EXTERNAL` is a truthful state, not a PASS substitute.

## 17. Handoff to NODE-72

NODE-72 may consume a NODE-71 decision only when the decision JSON says `passed=true` for the exact immutable RC SHA being deployed. Any code/image/migration change after acceptance creates a new RC and invalidates the previous production deployment approval.
