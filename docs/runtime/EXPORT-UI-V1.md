# Export Product UX Runtime V1

## Purpose

NODE-60 is a product surface over NODE-49. It does not implement a browser renderer, a second export database, or a floating-version resolver.

```text
Exact ArtifactVersion + exact DesignVersion
  -> ExportRequest
  -> NODE-49 ExportJob
  -> PENDING / RENDERING / PACKAGING / VALIDATING
  -> ExportResult / READY
  -> authorized short-lived download
```

## Source truth

Every request visibly freezes `artifact_version_id` and `design_document_version_id`. `latest`, `head`, and `current` are rejected. Export History repeats those IDs so an old delivery can be traced without consulting current project head state.

## Capability projection

The UI projects the verified NODE-49 V1 set: PNG, JPEG, WebP, SVG, PDF, ZIP Batch and LUMI Project Package. Content capability narrows that set: SVG is hidden for non-vector sources, and a batch source only receives formats with verified multi-frame semantics.

The UI intentionally does not advertise CMYK, Display P3, PSD, bleed or crop marks. JPEG never exposes alpha. No marketing-only format button is rendered.

## Geometry versus adaptation

NODE-49 owns `SCALE` and `CROP`. If requested width/height changes the aspect ratio, the UI presents those deterministic choices separately from **Adapt design with AI**. The AI action is a handoff to the Workspace with the exact input DesignVersion and target dimensions; that workflow must create a new DesignVersion before another export is created.

`DESIGN_ADAPTATION` is never placed inside ExportSpec.

## Job truth

The browser never synthesizes success. It renders service status and service progress only. Production HTTP mode creates a request and polls the existing job; deterministic non-production mode advances through the same canonical status names solely for repeatable browser tests.

A file is downloadable only from a READY job. Requesting a download asks the server for a fresh 30–900 second signed lease. That URL lives only in ephemeral React state; storage keys/signed URLs are not persisted by the browser.

## Manifest and provenance

When requested, NODE-49 creates the verified provenance manifest. The normal surface summarizes exact source IDs, BrandRuleSet binding and checksums; the actual manifest download remains one of the verified output files returned by the service.

## Cost

Export rendering itself is labeled as zero AI-generation cost. AI Adapt is explicitly a different version-producing workflow and must expose its own estimate before generation.

## Partial failure boundary

NODE-60's specification asks for frame/file-level partial retry, but NODE-49 V1 currently exposes only job-level `error_code` and has no item-level retry command. NODE-60 therefore **does not simulate partial retry**. The UI explains the boundary and supports a fresh exact-source export request. Product-level per-file retry remains an integration dependency until NODE-49 adds durable failed-item identity and retry semantics.

## Security

Safe user-facing error copy is allowlisted. Raw worker payloads, stack traces, system prompts, secrets and signed storage URLs are never stored as canonical UI history. Deterministic fixtures are gated by `NODE_ENV !== production && LUMI_EXPORT_UI_E2E=1`.
