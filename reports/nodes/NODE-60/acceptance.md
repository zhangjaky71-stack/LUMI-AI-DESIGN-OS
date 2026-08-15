# NODE-60 — Export Product UX Acceptance

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implementation evidence

Implementation commit: `263d23bc3874433956a1226e503888702a519bf1`

- `/app/projects/{projectId}/export` product route added.
- Exact ArtifactVersion + exact DesignVersion are visible and mandatory.
- Format buttons are capability-filtered; false V1 capabilities remain hidden.
- Size modes: original, 2×, custom and social presets.
- Aspect-ratio change explicitly separates SCALE/CROP from AI Adapt version handoff.
- JPEG alpha is fail-closed; quality/alpha controls are format-aware.
- Export estimate explicitly shows no AI-generation charge for export rendering.
- Job UI follows NODE-49 PENDING → RENDERING → PACKAGING → VALIDATING → READY/FAILED/EXPIRED.
- Download is READY-only and obtains a fresh short-lived signed lease without rerender.
- Export history keeps exact source IDs, file size/checksum and manifest availability.
- Safe production API errors preserve opaque `request_id` for support without exposing raw payloads.
- Browser durable export truth is prohibited; signed URL stays ephemeral.
- Deterministic browser fixture is non-production gated.
- Project page links to Export Center.

## Tests staged

- exact-version rejection;
- capability filtering;
- raster SVG/ZIP hiding;
- batch format filtering;
- aspect-ratio Crop/Scale vs AI Adapt;
- JPEG alpha fail-closed;
- canonical job lifecycle;
- signed URL refresh without rerender/new job;
- safe opaque request-id projection;
- zero AI export cost;
- mobile layout;
- NODE-49 engine regression suite;
- NODE-59 through NODE-54 browser regressions.

These suites are **STAGED**, not observed PASS, because the hosted runner did not start.

## Hosted pinned validation evidence

Workflow: **Export UI**  
Run: `31869111021`  
Run number: `1`  
Head SHA: `263d23bc3874433956a1226e503888702a519bf1`

| Job | Job/check ID | Result | Execution evidence |
| --- | ---: | --- | --- |
| `export-ui-contract` | `94974836754` | failure | `runner_id=0`, `runner_name=""`, `steps=[]` — runner never started |
| `export-ui-quality` | `94974842077` | skipped | dependency did not run |
| `export-ui-build` | `94974842423` | skipped | dependency did not run |
| `export-ui-browser-e2e` | `94974842236` | skipped | dependencies did not run |

GitHub check annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

Classification: **BLOCKED BEFORE RUNNER**.

This is an account/platform validation blocker. It is **not** a NODE-60 code/test failure and it is **not** a PASS. No checkout, install, validator, typecheck, unit, build, or browser step executed in this hosted run.

## Known canonical integration gap

NODE-49 V1 returns job-level failure only. It does not expose durable failed Frame/file identities or an item-level retry command. Therefore NODE-60 intentionally does not claim batch partial retry is implemented. This acceptance item stays open until the backend contract is extended and validated.

## Definition of Done

- [x] exact source + truthful capability UI implemented;
- [x] Crop/Scale and AI Adapt are separated;
- [x] real lifecycle-shaped UI and READY-only download contract implemented;
- [x] signed download refresh does not create a new export;
- [x] exact-version history/provenance summary implemented;
- [x] safe request-id projection without raw diagnostic leakage implemented;
- [x] print/PSD false claims hidden;
- [x] static/unit/browser coverage staged;
- [ ] per-file partial retry backend contract exists and is integrated;
- [ ] hosted pinned gates execute green;
- [ ] production Export HTTP endpoints + worker deployment are connected in the target environment.
