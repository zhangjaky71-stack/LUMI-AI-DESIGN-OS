# Brand Kit UI Runtime Contract V1

Status: NODE-58 core implemented, validating, not complete.

## 1. Truth boundaries

```text
brands table
  -> Brand registry resource + resource version

BrandRuleRepository / BrandRuleService
  -> immutable BrandRuleSet versions
  -> active_rule_set_version_id pointer
  -> cited BrandGuideProposal review/publish

Project resource
  -> canonical brand_id binding

Asset lifecycle / rights
  -> exact Asset identity and publication eligibility
```

Brand Kit UI is an editor/projection over these resources. It MUST NOT persist a parallel brand JSON document in the browser.

## 2. Brand resource

Brand identity is tenant-scoped and mutable with optimistic concurrency:

```text
GET /api/v1/brands
POST /api/v1/brands
GET /api/v1/brands/{brand_id}
PATCH /api/v1/brands/{brand_id}
If-Match: W/"<brand.version>"
```

PATCH runs under a row lock and exact version fence. The UI never writes `active_rule_set_version_id` directly.

## 3. BrandRuleSet version flow

Editing a published BrandRuleSet never changes it in place.

```text
Published vN
  -> derive editor state
  -> POST new Draft vN+1
  -> review draft state
  -> explicit POST publish
  -> BrandRuleService validates rights/state
  -> active pointer advances
```

Historical AgentRuns and Artifacts keep their frozen rule-set/version provenance.

## 4. Exact recovery

Brand Kit supports exact recovery routes:

```text
/brands?brand=<brand_id>
/brands?brand=<brand_id>&ruleset=<rule_set_id>
/brands?brand=<brand_id>&proposal=<proposal_id>
```

Active RuleSet is used only when no explicit `ruleset` is requested. A 404 active RuleSet is represented as “no published rules”, not fabricated defaults.

## 5. Controlled rule editor

The core rule UI writes only evaluator-supported parameter shapes:

- `ALLOWED_COLOR.colors`
- `FORBIDDEN_COLOR.colors`
- `MIN_CONTRAST.ratio`
- `FONT_ALLOWED.asset_ids/families`
- `LOGO_ALLOWED_ASSET.asset_ids`
- `LOGO_MIN_SIZE.min_width/min_height`
- `LOGO_CLEAR_SPACE.minimum`
- `LOGO_TRANSFORM.forbid_rotation/forbid_stretch/forbid_recolor`

Existing rule kinds outside this managed subset are carried forward unchanged into the next Draft. The UI does not offer raw arbitrary JSON editing.

## 6. Tokens / Palette

Brand tokens are versioned within the next RuleSet snapshot. Token IDs must be non-empty and unique. Color token editing and hard color allow/deny rules remain separate operations so changing a token cannot silently rewrite compliance policy.

## 7. Assets and rights

Logo/font/reference policy stores exact Asset IDs. Publication remains server-authoritative:

- fonts must exist;
- be READY;
- be `media_kind=font`;
- pass commercial-use rights;
- and require a rights reader when font assets are present.

NODE-58 does not accept arbitrary external URLs as a substitute for managed Assets.

Brand-scoped upload is not yet composed; the current Project-scoped Asset lifecycle cannot be truthfully presented as an independent Brand upload flow.

## 8. Brand Guide review

Guide extraction follows:

```text
source Asset
  -> INFERRED_PROPOSAL rules + citations
  -> PENDING_REVIEW
  -> human approve/reject
  -> APPROVED only
  -> publish_guide_proposal
  -> rules rewritten server-side as APPROVED_GUIDE_EXTRACTION
  -> new BrandRuleSet
```

The browser does not mutate inferred proposal source values to bypass review. It never exposes a one-click “PDF -> hard rules” publish action.

## 9. Project binding

`Project.brand_id` is the canonical project-to-brand binding. Changes use the Project resource version and `If-Match`. A project already bound to another Brand is fail-closed in the core UI; explicit reassignment UX is deferred rather than silently replacing the relationship.

Binding a Brand does not rewrite historical runs. Downstream runtime resolution/freeze semantics remain responsible for exact BrandRuleSet provenance.

## 10. CSRF / tenant safety

Both browser and server-side web API calls use the existing session cookies plus tenant header. Unsafe requests send the `lumi_csrf` double-submit value as `X-CSRF-Token` and preserve Origin validation. NODE-58 does not weaken the API auth guard.

## 11. Failure semantics

- Brand stale version -> HTTP 409, ask user to refresh/reconcile.
- Project stale version -> HTTP 409, no silent overwrite.
- Missing active RuleSet -> Brand exists with “No published rules”.
- Font rights unavailable/denied -> publication denied server-side.
- Unreviewed guide proposal -> publication denied.
- Brand registry factory absent -> 503 fail closed.
- Brand-scoped upload unavailable -> no fake upload control.
- Compliance observations unavailable -> no fake compliance score.

## 12. Remaining P0

See `reports/nodes/NODE-58/gap-ledger.json`: production registry composition, Brand-scoped Asset upload/picker/rights UI, Guide extraction creation/listing, RuleSet history/compare/rollback, licensed font/CJK controls, Canvas compliance preview, project exact-vs-current RuleSet policy, browser/Postgres E2E and hosted green CI.