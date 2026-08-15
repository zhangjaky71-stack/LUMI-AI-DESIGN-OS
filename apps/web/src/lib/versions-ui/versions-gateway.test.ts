import { describe, expect, it } from "vitest";
import { DeterministicVersionsGateway } from "./versions-gateway";
import { versionsSeed } from "./versions-server";

const ORG = "org-lumi";
const PROJECT = "project-summer-launch";

function gateway(projectId = PROJECT) {
  return new DeterministicVersionsGateway(versionsSeed(projectId));
}

describe("Deterministic Versions UI gateway", () => {
  it("restores an old version by appending a new DRAFT while preserving approved history", async () => {
    const runtime = gateway();
    const before = await runtime.getWorkspace(ORG, PROJECT);
    const main = before.branches.find((branch) => branch.name === "main")!;
    const restored = await runtime.restore(ORG, PROJECT, {
      artifact_id: before.active_artifact.id,
      branch_id: main.id,
      source_version_id: "design-v2",
      expected_head_version_id: main.head_version_id,
    });

    expect(restored.versions).toHaveLength(before.versions.length + 1);
    const newHead = restored.versions.find((item) => item.version.id === restored.head_version_id)!;
    expect(newHead.version.version_number).toBe(5);
    expect(newHead.version.status).toBe("DRAFT");
    expect(newHead.version.parent_version_id).toBe("design-v4");
    expect(restored.versions.find((item) => item.version.id === "design-v2")?.version.status).toBe("APPROVED");
    expect(restored.versions.some((item) => item.version.id === "design-v4")).toBe(true);
    expect(restored.lineage.some((edge) => edge.from_version_id === "design-v2" && edge.to_version_id === newHead.version.id && edge.type === "DERIVED_FROM")).toBe(true);
  });

  it("fails closed on a stale branch head before mutating restore history", async () => {
    const runtime = gateway();
    const before = await runtime.getWorkspace(ORG, PROJECT);
    const main = before.branches.find((branch) => branch.name === "main")!;
    await runtime.checkForUpdates(ORG, PROJECT, before.active_artifact.id);

    await expect(runtime.restore(ORG, PROJECT, {
      artifact_id: before.active_artifact.id,
      branch_id: main.id,
      source_version_id: "design-v2",
      expected_head_version_id: main.head_version_id,
    })).rejects.toMatchObject({ problem: { code: "BRANCH_HEAD_CONFLICT" } });

    const after = await runtime.getWorkspace(ORG, PROJECT);
    expect(after.versions).toHaveLength(before.versions.length + 1);
    expect(after.versions.filter((item) => item.safe_change_summary.includes("Restored immutable"))).toHaveLength(0);
  });

  it("forks an exact historical version without creating a fake merge or new content version", async () => {
    const runtime = gateway();
    const before = await runtime.getWorkspace(ORG, PROJECT);
    const next = await runtime.fork(ORG, PROJECT, {
      artifact_id: before.active_artifact.id,
      source_version_id: "design-v3",
      name: "Dark Direction",
    });
    const branch = next.branches.find((item) => item.name === "dark-direction")!;
    expect(branch.base_version_id).toBe("design-v3");
    expect(branch.head_version_id).toBe("design-v3");
    expect(next.versions).toHaveLength(before.versions.length);
    expect(next.active_branch_id).toBe(branch.id);
  });

  it("compares exact version identities using structured semantic changes", async () => {
    const runtime = gateway();
    const result = await runtime.compare(ORG, "artifact-campaign-canvas", "design-v2", "design-v4");
    expect(result.exact).toBe(true);
    expect(result.from_version_id).toBe("design-v2");
    expect(result.to_version_id).toBe("design-v4");
    expect(result.semantic_changes.some((change) => change.node_id === "node-offer" && change.property === "x")).toBe(true);
    expect(result.semantic_changes.some((change) => change.node_id === "node-headline" && change.property === "text")).toBe(true);
  });

  it("surfaces a concurrent new head without deleting historical compare targets", async () => {
    const runtime = gateway();
    const before = await runtime.getWorkspace(ORG, PROJECT);
    const updated = await runtime.checkForUpdates(ORG, PROJECT, before.active_artifact.id);
    expect(updated.concurrent_head_version_id).not.toBeNull();
    expect(updated.notice?.kind).toBe("WARNING");
    expect(updated.versions.some((item) => item.version.id === "design-v2")).toBe(true);
    expect(updated.versions.some((item) => item.version.id === "design-v4")).toBe(true);
    const compare = await runtime.compare(ORG, before.active_artifact.id, "design-v2", "design-v4");
    expect(compare.from_version_id).toBe("design-v2");
    expect(compare.to_version_id).toBe("design-v4");
  });

  it("returns only safe provenance projection and honors permission denial", async () => {
    const runtime = gateway();
    const provenance = await runtime.getProvenance(ORG, "design-v4");
    expect(provenance.agent_run_id).toBe("run-summer-21");
    expect(provenance.prompt_hash).toBe("d".repeat(64));
    const serialized = JSON.stringify(provenance);
    expect(serialized).not.toContain("system_prompt");
    expect(serialized).not.toContain("chain_of_thought");

    const denied = gateway("project-provenance-denied");
    await expect(denied.getProvenance(ORG, "design-v4")).rejects.toMatchObject({
      problem: { code: "PROVENANCE_FORBIDDEN", status: 403 },
    });
  });

  it("switches to raster Artifact history while preserving exact Artifact identity", async () => {
    const runtime = gateway();
    const raster = await runtime.getWorkspace(ORG, PROJECT, "artifact-hero-raster");
    expect(raster.active_artifact.type).toBe("RASTER_IMAGE");
    expect(raster.versions.map((item) => item.version.id)).toEqual(["raster-v3", "raster-v2", "raster-v1"]);
    const compare = await runtime.compare(ORG, raster.active_artifact.id, "raster-v1", "raster-v3");
    expect(compare.kind).toBe("RASTER");
  });
});
