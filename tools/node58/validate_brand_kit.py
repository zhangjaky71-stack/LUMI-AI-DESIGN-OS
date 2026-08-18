from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(path: str, *markers: str) -> None:
    text = read(path)
    missing = [marker for marker in markers if marker not in text]
    assert not missing, f"{path}: missing {missing}"


def forbid(path: str, *markers: str) -> None:
    text = read(path)
    found = [marker for marker in markers if marker in text]
    assert not found, f"{path}: forbidden {found}"


def main() -> None:
    require(
        "apps/api/src/lumi_api/api/v1/app.py",
        "brand_registry_router",
        "app.include_router(brand_registry_router",
    )
    require(
        "apps/api/src/lumi_api/api/v1/brand_registry_routes.py",
        '@router.get("", response_model=BrandPage)',
        '@router.post("", response_model=BrandResponse',
        '@router.patch("/{brand_id}"',
        "IfMatch",
        "parse_if_match",
        "version_etag",
    )
    require(
        "apps/api/src/lumi_api/api/v1/brand_registry_dependencies.py",
        "brand_registry_service_factory",
        "with factory() as service",
    )
    forbid(
        "apps/api/src/lumi_api/api/v1/brand_registry_dependencies.py",
        'getattr(request.app.state, "brand_registry_service", None)',
    )
    require(
        "apps/api/src/lumi_api/api/v1/brand_registry_adapter.py",
        "FROM brands",
        "FOR UPDATE",
        "expected_version",
        "brand_version_conflict",
        "version=version+1",
    )
    require(
        "apps/api/src/lumi_api/api/v1/brand_registry_factory.py",
        "session = self.session_factory()",
        "session.close()",
    )
    require(
        "apps/api/src/lumi_api/brand_rules/service.py",
        "def get_rule_set(",
        "def get_active_rule_set(",
        "def get_guide_proposal(",
        "INFERRED_PROPOSAL cannot become published without review",
        "font asset rights reader unavailable for publication",
    )
    require(
        "apps/api/src/lumi_api/api/v1/brand_rules_routes.py",
        '"/brands/{brand_id}/rule-sets/active"',
        '"/brands/{brand_id}/rule-sets/{rule_set_id}"',
        '"/brands/{brand_id}/guide-proposals/{proposal_id}"',
        '"/guide-proposals/{proposal_id}/review"',
        '"/guide-proposals/{proposal_id}/publish"',
    )
    require(
        "apps/web/src/lib/api/server.ts",
        'cookieStore.get("lumi_csrf")',
        'headers.set("x-csrf-token", csrf)',
        'headers.set("origin", origin)',
    )
    require(
        "apps/web/src/lib/projects/types.ts",
        "version?: number | null",
        "brandId?: string | null",
        "workspaceId?: string | null",
    )
    require(
        "apps/web/src/app/(shell)/brands/page.tsx",
        'scalar(params.brand)',
        'scalar(params.ruleset)',
        'scalar(params.proposal)',
        "getBrandRuleSet",
        "getGuideProposal",
    )
    require(
        "apps/web/src/components/brands/brand-studio.tsx",
        "Create new draft",
        "Publish draft",
        "createBrandDraft",
        "publishBrandRuleSet",
        "reviewGuideProposal",
        "publishGuideProposal",
        "bindProjectBrand",
        "allowedLogoAssetIds",
        "allowedFontAssetIds",
        "forbidLogoRotation",
        "INFERRED_PROPOSAL",
        "one-click",
        "brand-scoped upload",
    )
    forbid(
        "apps/web/src/components/brands/brand-studio.tsx",
        "URL.createObjectURL",
        "data:image/",
        "source: \"INFERRED_PROPOSAL\"",
    )
    require(
        "apps/web/src/lib/brands/client.ts",
        '"If-Match": `W/\\"${brand.version}\\"`',
        '"If-Match": `W/\\"${projectVersion}\\"`',
        "draftWire(input)",
    )
    require(
        "apps/web/src/components/shell/app-nav.tsx",
        'href: "/brands"',
        'label: "Brand Kit"',
    )
    for path in (
        "apps/api/tests/test_node58_brand_kit_contracts.py",
        "apps/web/src/lib/brands/types.test.ts",
        "apps/web/src/lib/projects/brand-binding.node58.test.ts",
    ):
        assert (ROOT / path).is_file(), f"missing test: {path}"

    spec = read("docs/nodes/NODE-58-BRAND-KIT-UI.md")
    assert "CORE IMPLEMENTED / VALIDATING / NOT COMPLETE" in spec
    print("NODE58_BRAND_KIT_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
