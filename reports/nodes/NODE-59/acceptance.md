# NODE-59 Acceptance — Version History, Compare & Branch UX

Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implemented acceptance evidence

- [x] Version History is a projection over NODE-42 Artifact Engine, not a second history store.
- [x] Default history payload omits Artifact file bucket/storage keys, full rights data and full ProvenanceRecord.
- [x] Version timeline exposes exact version IDs/numbers, branch/head, status/approval badge, creator, time and quality.
- [x] Design semantic summaries are derived from NODE-38 structured diff categories only.
- [x] Compare always binds exact left/right ArtifactVersion IDs.
- [x] Unknown compare metadata is not stringified into the UI.
- [x] User Fork cannot submit creator identity; authenticated actor is authoritative.
- [x] User Restore cannot submit creator identity or canonical provenance.
- [x] Restore provenance is server-derived and references the exact restored source version.
- [x] Restore forwards the client-known target branch head as the Artifact Engine CAS fence.
- [x] Restore response is a safe version summary, not a full ArtifactVersion/provenance payload.
- [x] Restore copy semantics remain NODE-42: a new version is created and later history is preserved.
- [x] Safe provenance endpoint excludes raw prompt, prompt_ref, provider_request_id, messages, private reasoning and raw tool output.
- [x] Browser independently rejects private provenance-like fields before parser ingestion.
- [x] Approved versions remain immutable canonical records; approval/status badge is read from ArtifactVersion.
- [x] Background history refresh detects a new branch head without automatically switching the current exact Canvas version or compare pair.
- [x] Workspace Inspector integrates the Versions panel for the selected exact Artifact.
- [x] Dedicated Python/TypeScript tests and static acceptance/CI assets are present.

## Hosted CI evidence — 2026-08-18

- Pull request: #126 (`feat/node-59-versions-ui` → `feat/node-58-brand-kit-ui`).
- NODE-59 workflow run: `32101439784`.
- `versions-contract` job: `95602582961`, conclusion `failure`, **0 executed steps**.
- Job step API returned an empty step list.
- Job log download returned `404 BlobNotFound`.
- `versions-web` was skipped because its dependency did not execute successfully.
- Therefore there is no evidence that a NODE-59 compile/test/lint/build command ran and failed. The hosted result is treated as a pre-run runner/account blocker, not as code-level failure evidence.

## Required before COMPLETE

- [ ] Canonical visual side-by-side / wipe / heatmap compare renderer.
- [ ] Structured before/after property values, not only changed property categories.
- [ ] Permission-aware approval audit detail projection.
- [ ] Exact BrandRuleSet version in public version provenance.
- [ ] Cursor pagination + virtualization for large histories.
- [ ] Browser E2E and PostgreSQL integration for version/fork/restore/compare/provenance/concurrency.
- [ ] Hosted GitHub Actions with executed green steps.

NODE-59 remains **NOT COMPLETE** until every open P0 gap in `gap-ledger.json` has executable evidence.
