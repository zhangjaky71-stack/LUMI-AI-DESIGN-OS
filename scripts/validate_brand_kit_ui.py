#!/usr/bin/env python3
"""Static architecture gate for NODE-58 Brand Kit Product UI."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "apps/web/src/components/brand-kit/brand-kit.tsx",
    "apps/web/src/components/brand-kit/brand-kit.module.css",
    "apps/web/src/lib/brand-kit/types.ts",
    "apps/web/src/lib/brand-kit/contracts.ts",
    "apps/web/src/lib/brand-kit/brand-kit-server.ts",
    "apps/web/src/lib/brand-kit/brand-kit-gateway.ts",
    "apps/web/src/lib/brand-kit/contracts.test.ts",
    "apps/web/src/lib/brand-kit/brand-kit-gateway.test.ts",
    "apps/web/src/lib/brand-kit/agent-brand-binding.test.ts",
    "apps/web/e2e/brand-kit.spec.ts",
    "docs/nodes/NODE-58-BRAND-KIT-UI.md",
    "docs/runtime/BRAND-KIT-UI-V1.md",
    "reports/nodes/NODE-58/acceptance.md",
]

errors: list[str] = []


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        errors.append(f"missing required file: {path}")
        return ""
    return target.read_text(encoding="utf-8")


for path in REQUIRED:
    read(path)

ui = read("apps/web/src/components/brand-kit/brand-kit.tsx")
gateway = read("apps/web/src/lib/brand-kit/brand-kit-gateway.ts")
contracts = read("apps/web/src/lib/brand-kit/contracts.ts")
types = read("apps/web/src/lib/brand-kit/types.ts")
workspace = read("apps/web/src/components/ai-workspace/ai-workspace.tsx")
workspace_gateway = read("apps/web/src/lib/ai-workspace/workspace-gateway.ts")
workspace_types = read("apps/web/src/lib/ai-workspace/types.ts")
workspace_page = read("apps/web/src/app/app/projects/[projectId]/workspace/page.tsx")
e2e = read("apps/web/e2e/brand-kit.spec.ts")
tsconfig = read("apps/web/tsconfig.json")

checks = [
    ("web consumes canonical Brand Rules package", '"@lumi/brand-rules"' in tsconfig and "from \"@lumi/brand-rules\"" in types),
    ("Brand Kit is a real app surface", "<BrandKitProduct" in read("apps/web/src/app/app/brands/page.tsx")),
    ("draft uses optimistic revision", "expected_draft_revision" in types and "DRAFT_REVISION_CONFLICT" in gateway),
    ("asset upload reuses governed lifecycle", '"/assets/uploads"' in gateway and "putPresignedObject" in gateway),
    ("asset upload records rights", "rights_assertion" in gateway and "UNKNOWN" in ui),
    ("palette duplicate and contrast checks exist", "duplicateColorTokenIds" in contracts and "contrastRatio" in contracts),
    ("font rights can block publish", "UNKNOWN" in contracts and "font" in contracts.lower()),
    ("guide extraction keeps citations", "createExtractionProposal" in gateway and "citations" in gateway),
    ("guide approval uses canonical review helper", "approveExtractionProposal" in gateway and "APPROVED_GUIDE_EXTRACTION" in e2e),
    ("unreviewed guide cannot silently become HARD", "GUIDE_REVIEW_INCOMPLETE" in gateway and "INFERRED_PROPOSAL" in contracts),
    ("publish creates versioned BrandRuleSet", "published_versions" in gateway and 'status: "PUBLISHED"' in gateway),
    ("project supports current and pinned binding", "CURRENT_PUBLISHED" in types and "PINNED" in gateway),
    ("compliance uses exact artifact + brand versions", "artifact_version_id" in types and "brand_rule_set_version" in types),
    ("stale brand version fails closed", "BRAND_RULE_VERSION_STALE" in gateway),
    ("compliance deep-link targets Canvas node", "focusNode=" in ui and "brandRuleVersion=" in ui and "focusNodeId" in workspace),
    ("workspace parses compliance deep link", "searchParams" in workspace_page and "brandRuleVersion" in workspace_page),
    ("Agent Run stores frozen brand version", "brand_rule_set_version" in workspace_types and "brand_rule_set_version:" in workspace_gateway),
    ("workspace displays frozen version", "· frozen" in workspace),
    ("browser covers guide review", "complete human review" in e2e),
    ("browser covers version publish", "new immutable version" in e2e),
    ("browser covers Canvas deep link", "exact Canvas node" in e2e),
    ("browser covers Run pinning", "freezes the resolved BrandRuleSet" in e2e),
]
for label, passed in checks:
    if not passed:
        errors.append(f"architecture check failed: {label}")

for forbidden in ("localStorage", "sessionStorage", "indexedDB"):
    if forbidden in ui or forbidden in gateway or forbidden in contracts:
        errors.append(f"Brand Kit must not create browser canonical truth: {forbidden}")

if "raw tool" in ui.lower() or "chain-of-thought" in ui.lower():
    errors.append("Brand Kit UI must not expose private execution internals")

if errors:
    print("NODE-58 Brand Kit validation FAILED")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("NODE-58 Brand Kit validation PASSED")
