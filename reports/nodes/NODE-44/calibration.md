# NODE-44 Calibration Evidence

Status: **CONFORMANCE FIXTURE IMPLEMENTED / PRODUCTION CALIBRATION PENDING REAL DATA**

## What this report proves

The shared fixture `fixtures/identity/node-44-calibration.json` proves that the TypeScript/Python calibration contract is explicit and reproducible. It includes positive, negative, and near-miss score distributions for Logo strict-preserve and Product background-replacement scenarios.

Expected fixture thresholds:

| Profile | Scenario | Positive | Negative | Near miss | Expected threshold |
|---|---|---:|---:|---:|---:|
| `logo-strict` | `STRICT_PRESERVE` | 3 | 2 | 2 | 92 |
| `product-background` | `BACKGROUND_REPLACEMENT` | 3 | 2 | 2 | 88 |

These values are intentionally simple synthetic conformance data. They are **not** evidence that 92 or 88 is an appropriate production operating point.

## Algorithm contract

For each identity type + scenario the runtime:

1. requires at least one positive and at least one negative/near-miss sample;
2. evaluates candidate thresholds derived from observed scores;
3. calculates precision, recall, F1, false-positive rate and false-negative rate;
4. records ROC AUC and average precision;
5. optionally enforces minimum precision/recall objectives;
6. selects a deterministic operating point;
7. persists profile, dataset, model-bundle and preprocessor versions.

P0 Product and Logo profiles must require multiple independent signals.

## Production calibration gate

Before NODE-44 can be treated as fully production-calibrated, a real benchmark must be assembled from approved/rights-compatible assets per supported use case. At minimum it should include:

- exact canonical logo/product views;
- supported angle/lighting/background variation positives;
- stretched, recolored and partially obscured logo near misses;
- same family but wrong SKU/product negatives;
- packaging/logo/text alteration negatives;
- low-resolution and bad-crop cases;
- detector misses;
- historical provider/model version comparisons.

A reviewer must explicitly choose the operating point based on false-positive/false-negative business cost. Model upgrades require a new calibration profile/version; they do not mutate historical reports.

## Current decision

Repository conformance/calibration machinery: **IMPLEMENTED**.

Real-world production threshold dataset: **not claimed complete**. This distinction is intentional and prevents synthetic fixture numbers from becoming accidental product policy.
