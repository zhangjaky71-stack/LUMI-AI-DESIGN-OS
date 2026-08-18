# NODE-56 Acceptance — Layers / Inspector

Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implemented acceptance evidence

- [x] Canvas and Layers use one `CanvasController.selection` and synchronize both directions.
- [x] Layer Tree derives from current local DesignDocument projection rather than a second persisted tree.
- [x] Layer rows use bounded fixed-row virtualization with search and selected-row reveal.
- [x] Layer rename / visibility / lock use the existing typed Canvas operation path.
- [x] Inspector exposes x/y/w/h/rotation with numeric validation and Enter/blur commit.
- [x] Multi-select common values render mixed state rather than a fabricated value.
- [x] Multi-target geometry edits call `CanvasController.commitBatch` and enter NODE-55 autosave as one descriptor group.
- [x] Mixed locked selection blocks property batches; it does not silently edit only an unlocked subset.
- [x] Text content uses typed `SET_TEXT` and the existing cross-runtime safe wire mapping.
- [x] Constraint UI explicitly states NODE-39/server enforcement is authoritative.
- [x] Missing constraint provenance is displayed as `UNRESOLVED`, never guessed.
- [x] Brand token evidence is read-only in the core slice; no silent detach path exists.
- [x] Agent selection remains invalid while Canvas is dirty/saving/offline/conflict and uses the server-acknowledged revision only when saved.
- [x] Pure 10k layer virtualization contract and Canvas SDK batch surface have dedicated tests.
- [x] Static acceptance validator exists at `tools/node56/validate_layers_inspector.py`.

## Required before COMPLETE

- [ ] Production hierarchy mutation compiler and UI: reorder / reparent / group / ungroup.
- [ ] Full TextStyle and licensed font controls.
- [ ] Effective constraint projection with source/reason/severity and exact-version override UX.
- [ ] Explicit brand binding update-target vs detach UX.
- [ ] Browser E2E against composed PostgreSQL Canvas service.
- [ ] Real 10k DOM/scroll/frame-time performance acceptance.
- [ ] Hosted GitHub Actions run with executed steps and green evidence.

The node must remain **NOT COMPLETE** until every P0 item in `gap-ledger.json` is closed with evidence.