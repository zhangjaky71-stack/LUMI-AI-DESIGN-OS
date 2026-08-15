#!/usr/bin/env python3
"""Static architecture and safety gate for NODE-57 Agent Timeline."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "apps/web/src/components/agent-timeline/agent-timeline.tsx",
    "apps/web/src/components/agent-timeline/agent-timeline.module.css",
    "apps/web/src/lib/agent-timeline/types.ts",
    "apps/web/src/lib/agent-timeline/projector.ts",
    "apps/web/src/lib/agent-timeline/projector.test.ts",
    "apps/web/e2e/agent-timeline.spec.ts",
    "docs/nodes/NODE-57-AGENT-TIMELINE.md",
    "docs/runtime/AGENT-TIMELINE-V1.md",
    "reports/nodes/NODE-57/acceptance.md",
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

workspace = read("apps/web/src/components/ai-workspace/ai-workspace.tsx")
timeline = read("apps/web/src/components/agent-timeline/agent-timeline.tsx")
projector = read("apps/web/src/lib/agent-timeline/projector.ts")
types = read("apps/web/src/lib/ai-workspace/types.ts")
server = read("apps/web/src/lib/ai-workspace/workspace-server.ts")
e2e = read("apps/web/e2e/agent-timeline.spec.ts")

checks = [
    ("workspace mounts canonical timeline", "<AgentTimeline" in workspace),
    ("timeline derives from workspace snapshot", "projectAgentTimeline(snapshot" in timeline),
    ("run/task canonical model retained", "AgentRunSnapshot" in types and "AgentTaskSummary" in types),
    ("safe observability model excludes raw payload fields", "AgentToolSummary" in types and "safe_summary" in types),
    ("frontend redaction guard exists", "sanitizeTimelineText" in projector and "PRIVATE_EXECUTION_PATTERNS" in projector),
    ("real progress counts used", "completed_units" in projector and "total_units" in projector),
    ("waiting approval is sticky", "WAITING_USER" in projector and "sticky: waiting" in projector),
    ("artifact exact versions retained", "artifact_version_ids" in projector and "artifact.version_id" in timeline),
    ("retry action remains versioned gateway path", "onRetryTask" in timeline and "retryTask" in workspace),
    ("provider fallback is user-visible", "PROVIDER_FALLBACK" in projector),
    ("cancelled run fixture exists", "project-agent-cancelled" in server),
    ("refresh restoration browser case exists", "restores after refresh" in e2e),
    ("duplicate SSE browser case exists", "deduplicates realtime delivery" in e2e),
    ("no invented percentage fixture", "99%|100%" in e2e),
]
for label, passed in checks:
    if not passed:
        errors.append(f"architecture check failed: {label}")

for forbidden in ("localStorage", "sessionStorage", "indexedDB"):
    if forbidden in timeline or forbidden in projector:
        errors.append(f"Timeline must not create durable browser event truth: {forbidden}")

for forbidden in ("tool_payload", "tool_args", "stack_trace", "reasoning_trace"):
    if forbidden in timeline:
        errors.append(f"Timeline UI must not render private execution field: {forbidden}")

if errors:
    print("NODE-57 Agent Timeline validation FAILED")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("NODE-57 Agent Timeline validation PASSED")
