# NODE-58 Acceptance — Brand Kit UI

Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implemented acceptance evidence

- [x] Brand registry uses the existing tenant-scoped `brands` table rather than browser-local brand JSON.
- [x] Brand PATCH is version fenced with `If-Match`, PostgreSQL `FOR UPDATE`, and version increment.
- [x] Brand registry dependency is request-scoped and fails closed if production composition is absent.
- [x] Active and exact BrandRuleSet reads recover immutable rule snapshots after refresh.
- [x] Exact BrandGuideProposal read recovers cited proposal review state.
- [x] BrandRuleService still rejects `INFERRED_PROPOSAL` publication outside the human-reviewed guide path.
- [x] Font publication remains rights-gated and fails closed when the rights reader/assets are unavailable or invalid.
- [x] Brand Studio edits create a new Draft; Publish is a separate explicit action.
- [x] Rule editor emits only documented Brand compliance parameter shapes and preserves unmanaged canonical rules.
- [x] Palette, Logo/Font/reference Asset policy, Voice and VisualStyle are represented by versioned BrandRuleSet fields.
- [x] Guide Review shows proposal rules and citations and exposes approve/reject before publish.
- [x] Project binding uses canonical `Project.brand_id` plus Project resource version/If-Match.
- [x] Unsafe server-side web API requests forward the CSRF double-submit token and Origin; auth policy is not weakened.
- [x] Brand page supports exact `brand`, `ruleset`, and `proposal` recovery query parameters.
- [x] Brand-scoped Asset upload is not faked; the UI explicitly states the current lifecycle gap.
- [x] Dedicated API/Web contract tests and static acceptance validator exist.

## Required before COMPLETE

- [ ] Compose `PostgresBrandRegistryServiceFactory` into the production FastAPI application using the canonical Session factory.
- [ ] Brand-scoped Logo/Font/PDF upload, READY state, asset picker and rights metadata UI.
- [ ] Brand Guide PDF extraction/import creation plus proposal list/discovery.
- [ ] RuleSet version list/history/compare/rollback and automatic exact-draft URL update.
- [ ] Licensed font selection, role mapping and CJK fallback management.
- [ ] Real BrandCompliance preview from Canvas/DesignIR observations with violation navigation.
- [ ] Project policy UI for exact RuleSet version vs follow-current and visible run freeze semantics.
- [ ] Browser/PostgreSQL E2E for stale versions, publication rights, proposal review and Project binding.
- [ ] Hosted GitHub Actions with executed green steps.

NODE-58 remains **NOT COMPLETE** until every P0 gap in `gap-ledger.json` is closed with evidence.