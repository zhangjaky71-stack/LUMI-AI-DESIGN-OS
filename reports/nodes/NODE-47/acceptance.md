# NODE-47 Acceptance — Image Edit & Local Edit Pipeline

Status: **IMPLEMENTED / VALIDATING / not COMPLETE**

Base: `node-46-image-generation-release`

## Acceptance matrix

| Requirement | Evidence | Status |
|---|---|---|
| Structural edit priority | `planner.py`, tests | Implemented |
| Structural edit invokes no model | pipeline/test | Implemented |
| Mask source/version/checksum/dimensions pin | `model.py`, `mask.py` | Implemented |
| User/IR/detector/agent mask provenance | `MaskSource` | Implemented |
| High-impact mask preview approval | `MaskSpec` | Implemented |
| HARD protected overlap preflight | `mask.py` | Implemented |
| Multi-capability provider routing | Model Gateway router + adapter | Implemented |
| image.edit / image.mask_edit boundary | adapter | Implemented |
| Protected region postflight | delegated validator | Implemented |
| Identity postflight | NODE-44 delegate | Implemented |
| QR locked fail-closed | validator + test | Implemented |
| OCR locked text fail-closed | validator | Implemented |
| Intended region must change | validator delegate | Implemented |
| Resolution preserved | validator | Implemented |
| Protected compositing fallback | pipeline + test | Implemented |
| Source ArtifactVersion never overwritten | Artifact adapter + SQL | Implemented |
| PASS-only branch-head advance | Artifact adapter + test | Implemented |
| REPAIR stays DRAFT | test | Implemented |
| REJECT stays off branch head | test | Implemented |
| EDITED_FROM lineage | Artifact adapter + test | Implemented |
| Canvas REPLACE_ASSET after pixel PASS | pipeline + test | Implemented |
| Operation retry idempotency | repository + tests | Implemented |
| Async pending recovery | pipeline + test | Implemented |
| Cost record before postflight acceptance | pipeline | Implemented |
| 100+ golden cases | 125-case fixture | Implemented synthetic suite |
| Dedicated CI | `.github/workflows/image-edit.yml` | Implemented; hosted runner blocked |
| Live provider protected-edit quality benchmark | NODE-23 benchmark evidence | **Pending** |

## Golden quality honesty

The 125-case fixture validates control-plane contracts. It does not demonstrate real model pixel fidelity. Production completion requires live provider/model evidence for product/logo/QR preservation and requested-region edit success.

## Hosted validation evidence — initial release HEAD

```text
head_sha: 4af0bf1e59aa4ede5230cc661079d425d1c37fef
workflow: Image Edit
run_id: 31802510811
image-edit-contract job_id: 94773573139
conclusion: failure
runner_id: 0
steps: []
image-edit-quality: skipped
image-edit-integration: skipped
image-edit-benchmark: skipped
```

GitHub annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

This is an external GitHub Actions account/billing blocker. The runner never started, so there is no hosted evidence of a pytest, Pyright, Ruff, static-validator, PostgreSQL migration, 125-case golden suite, or benchmark failure. It is also not PASS.

Root `uv.lock` remains unchanged at SHA `43ca410851428ad00cd7e42ac57c2c12f1fb8666`.

## Completion blockers

1. Hosted NODE-47 workflow must actually execute green.
2. A selected production edit provider/model revision must have approved live protected-edit benchmark evidence.

Current decision: **IMPLEMENTED / VALIDATING / not COMPLETE**.
