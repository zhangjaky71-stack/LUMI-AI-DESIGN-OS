import { describe, expect, it } from "vitest";
import { DeterministicAIWorkspaceGateway } from "./workspace-gateway";
import type { DeterministicWorkspaceSeed } from "./types";

function seed(): DeterministicWorkspaceSeed {
  return {
    stale_approval_id: "approval-stale",
    snapshot: {
      project_id: "project-1",
      project_name: "Project",
      brand_name: "Brand",
      document: {
        document_id: "document-1",
        version: 4,
        title: "Canvas",
        width: 1200,
        height: 1500,
        selection_options: [
          { node_id: "node-product", label: "Product", kind: "image", locked_identity: true },
        ],
      },
      references: [],
      run: null,
      messages: [],
      artifacts: [],
      approvals: [
        {
          approval_id: "approval-stale",
          run_id: "old-run",
          expected_run_version: 1,
          state: "STALE",
          title: "Old",
          description: "Old approval",
          impact: null,
          estimated_cost_microusd: null,
          artifact_version_ids: [],
          expires_at: "2026-08-14T00:00:00.000Z",
        },
      ],
    },
  };
}

async function start(gateway: DeterministicAIWorkspaceGateway) {
  return gateway.startRun("org-lumi", {
    project_id: "project-1",
    prompt: "只改选中的产品区域，保持身份一致",
    selected_node_ids: ["node-product"],
    document_version: 4,
    reference_asset_ids: [],
    reference_artifact_version_ids: [],
  });
}

describe("DeterministicAIWorkspaceGateway", () => {
  it("preserves selected node ids and exact document version in a new run", async () => {
    const gateway = new DeterministicAIWorkspaceGateway(seed());
    const workspace = await start(gateway);
    expect(workspace.run?.selected_node_ids).toEqual(["node-product"]);
    expect(workspace.run?.document_version).toBe(4);
    expect(workspace.messages.at(-1)?.kind).toBe("USER");
  });

  it("supports pause/resume/stop with optimistic run-version checks", async () => {
    const gateway = new DeterministicAIWorkspaceGateway(seed());
    const started = await start(gateway);
    const run = started.run!;
    const paused = await gateway.pauseRun("org-lumi", {
      run_id: run.run_id,
      expected_run_version: run.version,
    });
    expect(paused.status).toBe("PAUSED");
    await expect(
      gateway.resumeRun("org-lumi", { run_id: run.run_id, expected_run_version: run.version }),
    ).rejects.toMatchObject({ problem: { code: "RUN_VERSION_CONFLICT" } });
    const resumed = await gateway.resumeRun("org-lumi", {
      run_id: paused.run_id,
      expected_run_version: paused.version,
    });
    expect(resumed.status).toBe("RUNNING");
    const stopped = await gateway.stopRun("org-lumi", {
      run_id: resumed.run_id,
      expected_run_version: resumed.version,
    });
    expect(stopped.status).toBe("CANCELED");
  });

  it("streams from Last-Event-ID and emits a duplicate event for dedupe coverage", async () => {
    const gateway = new DeterministicAIWorkspaceGateway(seed());
    const started = await start(gateway);
    const ids: string[] = [];
    await gateway.streamRun("org-lumi", "project-1", started.run!.run_id, {
      last_event_id: `${started.run!.run_id}:1`,
      signal: new AbortController().signal,
      on_event: (event) => ids.push(event.id),
    });
    expect(ids[0]).toBe(`${started.run!.run_id}:2`);
    expect(ids.filter((id) => id.endsWith(":2"))).toHaveLength(2);
    expect(ids).not.toContain(`${started.run!.run_id}:1`);
  });

  it("rejects stale approvals rather than accepting an old decision", async () => {
    const gateway = new DeterministicAIWorkspaceGateway(seed());
    await start(gateway);
    await expect(
      gateway.decideApproval("org-lumi", {
        approval_id: "approval-stale",
        run_id: "old-run",
        expected_run_version: 1,
        decision: "APPROVE",
        request_changes_note: null,
      }),
    ).rejects.toMatchObject({ problem: { code: "APPROVAL_STALE" } });
  });

  it("requires an exact artifact version and current document version for placement", async () => {
    const gateway = new DeterministicAIWorkspaceGateway(seed());
    const started = await start(gateway);
    const events: string[] = [];
    await gateway.streamRun("org-lumi", "project-1", started.run!.run_id, {
      last_event_id: null,
      signal: new AbortController().signal,
      on_event: (event) => events.push(event.id),
    });
    expect(events.length).toBeGreaterThan(0);
    const current = await gateway.getWorkspace("org-lumi", "project-1");
    const artifact = current.artifacts[0]!;
    await expect(
      gateway.placeArtifact("org-lumi", {
        project_id: "project-1",
        document_id: current.document.document_id,
        expected_document_version: current.document.version - 1,
        artifact_id: artifact.artifact_id,
        artifact_version_id: artifact.version_id,
      }),
    ).rejects.toMatchObject({ problem: { code: "DOCUMENT_VERSION_CONFLICT" } });
    const placed = await gateway.placeArtifact("org-lumi", {
      project_id: "project-1",
      document_id: current.document.document_id,
      expected_document_version: current.document.version,
      artifact_id: artifact.artifact_id,
      artifact_version_id: artifact.version_id,
    });
    expect(placed.document.version).toBe(current.document.version + 1);
    expect(placed.messages.at(-1)?.artifact_version_id).toBe(artifact.version_id);
  });
});
