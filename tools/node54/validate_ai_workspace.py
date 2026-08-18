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
        "agent_workspace_router",
        "app.include_router(agent_workspace_router",
    )
    require(
        "apps/api/src/lumi_api/api/v1/agent_workspace_routes.py",
        '"/{agent_run_id}/control"',
        '"/{agent_run_id}/events"',
        'Header(alias="Last-Event-ID"',
        'media_type="text/event-stream"',
        '"X-Accel-Buffering": "no"',
    )
    require(
        "apps/api/src/lumi_api/api/v1/agent_workspace_schemas.py",
        "SafeAgentEventType",
        '"chain_of_thought"',
        "AGENT_WORKSPACE_PRIVATE_EVENT_FIELD_FORBIDDEN",
    )
    require(
        "apps/api/src/lumi_api/api/v1/agent_workspace_adapter.py",
        "RunControlReader",
        "AgentEventReplayPort",
        "_public_interrupt",
        "agent_event_scope_mismatch",
    )

    require(
        "apps/web/src/lib/workspace/types.ts",
        "SAFE_AGENT_EVENT_TYPES",
        '"chain_of_thought"',
        "RUN_EVENT_PRIVATE_FIELD_FORBIDDEN",
        "design_document_version",
        "selected_node_ids",
    )
    require(
        "apps/web/src/lib/workspace/stream.ts",
        '"Last-Event-ID"',
        "ReadableStream<Uint8Array>",
        "consumeSse",
        "reconnectDelay",
    )
    forbid(
        "apps/web/src/lib/workspace/stream.ts",
        "new EventSource",
        "localStorage",
        "sessionStorage",
    )
    require(
        "apps/web/src/lib/workspace/reducer.ts",
        'event.eventType === "artifact.created"',
        "artifact_version_id",
        "Artifact event omitted an exact artifact version",
        "seenEventIds",
    )
    require(
        "apps/web/src/components/workspace/ai-workspace.tsx",
        "getRunControl(organizationId, runId)",
        "fresh.resumeVersion === expectedResumeVersion",
        'value: { action: "approve" }',
        "Provider work already accepted externally may still require reconciliation",
        "NODE-55 selection will bind here",
    )
    forbid(
        "apps/web/src/components/workspace/ai-workspace.tsx",
        "localStorage",
        "sessionStorage",
        "dangerouslySetInnerHTML",
    )
    require(
        "apps/web/src/app/(shell)/workspace/page.tsx",
        "requireAppSession()",
        "getProject(projectId)",
        "initialRunId={runId}",
    )
    require(
        "apps/web/src/lib/projects/api.ts",
        '"X-Organization-ID": session.organization.id',
    )

    for path in (
        "apps/web/src/lib/workspace/types.test.ts",
        "apps/web/src/lib/workspace/reducer.test.ts",
        "apps/web/src/lib/workspace/stream.test.ts",
        "apps/api/tests/test_node54_agent_workspace_contracts.py",
    ):
        assert (ROOT / path).is_file(), f"missing test: {path}"

    print("NODE54_AI_WORKSPACE_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
