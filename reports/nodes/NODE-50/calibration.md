# NODE-50 Calibration Report

Status: **CONTRACT CALIBRATION IMPLEMENTED / PRODUCTION HUMAN CALIBRATION PENDING**

## What is calibrated in this node

NODE-50 commits a fixed 40-sample corpus at:

`fixtures/quality/node-50-calibration.json`

The fixture is explicitly labeled:

`SYNTHETIC_HUMAN_LABEL_STRUCTURE`

It is used to prove that grader calibration is executable and version-bound. It does **not** claim that a production visual model has already been validated by real human reviewers.

## Pinned fixture

```text
grader_id: critic-vlm
grader_version: 2.1.0
dataset_version: human-pairs-2026-08
threshold: 75
sample_count: 40
PASS labels: 20
FAIL labels: 20
```

Expected deterministic confusion matrix at the pinned threshold:

```text
TP = 18
FN = 2
FP = 1
TN = 19
```

Expected metrics:

```text
precision           0.9473684210526315
recall              0.9000000000000000
F1                  0.9230769230769231
false positive rate 0.0500000000000000
false negative rate 0.1000000000000000
inter-rater field   0.85 (fixture contract value)
```

`calibration-fixture.test.ts` recomputes these metrics from sample labels/scores; it does not trust the Markdown values.

## Runtime safeguards

An accepted visual grade must match the approved calibration on:

```text
grader_id
grader_version
calibration_dataset_version
```

The runtime also rejects:

- sample count < 20；
- invalid probability metrics；
- `approved=true` with F1 < 0.60；
- `approved=true` with inter-rater agreement < 0.50；
- model/grader calibration version drift。

These are minimum software contract floors only. They are not production-quality targets.

## Production promotion gate

Before a live VLM is permitted to contribute to automated production approval, replace/add the synthetic corpus with a real versioned study:

1. blinded human pairwise/absolute labels；
2. documented reviewer instructions and anchor examples；
3. sufficient sample coverage by profile and failure type；
4. inter-rater agreement calculation from actual reviewer labels；
5. FP/FN analysis with special emphasis on hard-impact false passes；
6. threshold selection and rationale；
7. separate holdout set；
8. model + prompt + preprocessor version pinning；
9. NODE-05 baseline-vs-candidate release gate；
10. rerun on any model/prompt/calibration dataset change。

Until that evidence exists, Visual Critic may still use deterministic/NODE-39/43/44 signals and may use a VLM for advisory/review assistance, but this report does not authorize a production VLM to become the sole auto-approval authority.
