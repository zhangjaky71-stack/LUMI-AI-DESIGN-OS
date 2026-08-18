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
        "apps/api/src/lumi_api/api/v1/agent_workspace_schemas.py",
        "AGENT_WORKSPACE_PRIVATE_EVENT_FIELD_FORBIDDEN",
        '"api_key"',
        '"access_token"',
        '"authorization"',
        '"headers"',
        "_FORBIDDEN_KEY_FRAGMENTS",
    )
    require(
        "apps/web/src/lib/workspace/types.ts",
        "taskId",
        "FORBIDDEN_KEY_FRAGMENTS",
        "RUN_EVENT_PRIVATE_FIELD_FORBIDDEN",
    )
    require(
        "apps/web/src/lib/workspace/timeline.ts",
        "canonicalTimelineItem",
        "eventTimelineItem",
        "progressCounts",
        "retrySummary",
        "costSummary",
        "toolAction",
        "exactArtifactFromPayload",
        "publicSummary",
    )
    forbid(
        "apps/web/src/lib/workspace/timeline.ts",
        "JSON.stringify(payload)",
        "Math.round(progress * 100)",
        "chain_of_thought",
        "raw_response",
        "tool_output",
    )
    require(
        "apps/web/src/components/workspace/agent-timeline.tsx",
        "Current stage",
        "Run activity",
        "Open exact artifact",
        "Approve & continue",
        "Private reasoning, raw tool payloads, secrets and stack traces are never rendered",
    )
    require(
        "apps/web/src/components/workspace/ai-workspace.tsx",
        "<AgentTimeline",
        "control={runtime.control}",
        "items={runtime.timeline}",
        "runtime.control?.taskId",
    )
    require(
        "apps/web/src/lib/workspace/stream.test.ts",
        "deduplicates replay",
        "Last-Event-ID",
    )
    for path in (
        "apps/web/src/lib/workspace/timeline.test.ts",
        "apps/web/src/lib/workspace/types.test.ts",
        "apps/web/src/lib/workspace/reducer.test.ts",
        "apps/api/tests/test_node57_agent_timeline_contracts.py",
    ):
        assert (ROOT / path).is_file(), f"missing test: {path}"

    spec = read("docs/nodes/NODE-57-AGENT-TIMELINE.md")
    assert "CORE IMPLEMENTED / VALIDATING / NOT COMPLETE" in spec
    print("NODE57_AGENT_TIMELINE_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
