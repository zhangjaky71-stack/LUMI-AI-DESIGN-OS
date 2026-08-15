#!/usr/bin/env python3
"""Static architecture gate for NODE-54 AI Design Workspace."""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "apps/web/src/app/app/projects/[projectId]/workspace/page.tsx",
    "apps/web/src/components/ai-workspace/ai-workspace.tsx",
    "apps/web/src/components/ai-workspace/ai-workspace.module.css",
    "apps/web/src/lib/ai-workspace/types.ts",
    "apps/web/src/lib/ai-workspace/contracts.ts",
    "apps/web/src/lib/ai-workspace/workspace-gateway.ts",
    "apps/web/src/lib/ai-workspace/workspace-server.ts",
    "apps/web/src/lib/ai-workspace/contracts.test.ts",
    "apps/web/src/lib/ai-workspace/workspace-gateway.test.ts",
    "apps/web/e2e/ai-workspace.spec.ts",
    "docs/runtime/AI-WORKSPACE-V1.md",
    "reports/nodes/NODE-54/acceptance.md",
]

errors: list[str] = []


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        errors.append(f"missing required file: {path}")
        return ""
    return target.read_text(encoding="utf-8")


for required in REQUIRED:
    read(required)

route = read("apps/web/src/app/app/projects/[projectId]/workspace/page.tsx")
project_page = read("apps/web/src/app/app/projects/[projectId]/page.tsx")
component = read("apps/web/src/components/ai-workspace/ai-workspace.tsx")
contracts = read("apps/web/src/lib/ai-workspace/contracts.ts")
gateway = read("apps/web/src/lib/ai-workspace/workspace-gateway.ts")
server = read("apps/web/src/lib/ai-workspace/workspace-server.ts")
types = read("apps/web/src/lib/ai-workspace/types.ts")
e2e = read("apps/web/e2e/ai-workspace.spec.ts")

checks = [
    ("route renders AIWorkspace", "<AIWorkspace" in route),
    ("project detail exposes Workspace entry", "/workspace" in project_page and "进入 AI Workspace" in project_page),
    ("bootstrap remains server selected", "getAIWorkspaceBootstrap" in route),
    (
        "E2E adapter is forbidden in production",
        'process.env.NODE_ENV !== "production"' in server
        and 'process.env.LUMI_AI_WORKSPACE_E2E === "1"' in server,
    ),
    ("production defaults to HTTP", '{ mode: "http", seed: null }' in server),
    ("SSE uses Last-Event-ID", 'headers.set("last-event-id"' in gateway),
    ("SSE keeps same-origin credentials", 'credentials: "same-origin"' in gateway),
    ("SSE carries tenant scope", '"x-lumi-organization-id"' in gateway),
    ("SSE events are deduplicated", "seen_event_ids.includes(event.id)" in contracts),
    ("canonical refetch follows stream", "refreshCanonical" in component),
    ("selected node ids enter start payload", "selected_node_ids: selectedNodeIds" in component),
    ("document version enters start payload", "document_version: snapshot.document.version" in component),
    ("run controls are version checked", "expected_run_version" in gateway and "RUN_VERSION_CONFLICT" in gateway),
    ("stale approvals are blocked", "isApprovalActionable" in contracts and "APPROVAL_STALE" in gateway),
    (
        "artifact placement is exact-versioned",
        "artifact_version_id" in gateway and "expected_document_version" in gateway,
    ),
    ("mobile focused panels exist", "mobileTabs" in component and "mobilePanel" in component),
    ("provider warning has E2E coverage", "provider fallback warning" in e2e),
]
for label, passed in checks:
    if not passed:
        errors.append(f"architecture check failed: {label}")

forbidden_field_patterns = [
    r"\bchain_of_thought\s*[?:]",
    r"\breasoning_trace\s*[?:]",
    r"\bprivate_reasoning\s*[?:]",
    r"\bsystem_prompt\s*[?:]",
]
for pattern in forbidden_field_patterns:
    if re.search(pattern, types, re.IGNORECASE):
        errors.append(f"private reasoning/system prompt field exposed by workspace types: {pattern}")

for forbidden in ("localStorage", "indexedDB", "sessionStorage"):
    if forbidden in gateway or forbidden in component:
        errors.append(f"browser durable state forbidden for canonical workspace state: {forbidden}")

if errors:
    print("NODE-54 AI Workspace validation FAILED")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("NODE-54 AI Workspace validation PASSED")
