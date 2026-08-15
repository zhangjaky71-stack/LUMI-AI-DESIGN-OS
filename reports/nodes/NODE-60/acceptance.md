# NODE-60 — Export Product UX Acceptance

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implementation evidence

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
- zero AI export cost;
- mobile layout;
- NODE-49 engine regression suite;
- NODE-59 through NODE-54 browser regressions.

## Known canonical integration gap

NODE-49 V1 returns job-level failure only. It does not expose durable failed Frame/file identities or an item-level retry command. Therefore NODE-60 intentionally does not claim batch partial retry is implemented. This acceptance item stays open until the backend contract is extended and validated.

## Definition of Done

- [x] exact source + truthful capability UI implemented;
- [x] Crop/Scale and AI Adapt are separated;
- [x] real lifecycle-shaped UI and READY-only download contract implemented;
- [x] signed download refresh does not create a new export;
- [x] exact-version history/provenance summary implemented;
- [x] print/PSD false claims hidden;
- [x] static/unit/browser coverage staged;
- [ ] per-file partial retry backend contract exists and is integrated;
- [ ] hosted pinned gates execute green;
- [ ] production Export HTTP endpoints + worker deployment are connected in the target environment.

Hosted evidence will be appended after the implementation commit triggers GitHub Actions.
