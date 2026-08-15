import { describe, expect, it } from "vitest";
import { DeterministicAIWorkspaceGateway } from "@/lib/ai-workspace/workspace-gateway";
import { getAIWorkspaceBootstrap } from "@/lib/ai-workspace/workspace-server";

describe("Brand Kit → Agent Run binding", () => {
  it("freezes the resolved BrandRuleSet version on Run creation", async () => {
    const previous = process.env.LUMI_AI_WORKSPACE_E2E;
    process.env.LUMI_AI_WORKSPACE_E2E = "1";
    const bootstrap = getAIWorkspaceBootstrap("project-summer-launch");
    if (previous === undefined) delete process.env.LUMI_AI_WORKSPACE_E2E;
    else process.env.LUMI_AI_WORKSPACE_E2E = previous;
    if (!bootstrap.seed) throw new Error("workspace seed missing");

    const gateway = new DeterministicAIWorkspaceGateway(bootstrap.seed);
    const before = await gateway.getWorkspace("org-lumi", "project-summer-launch");
    expect(before.brand_binding?.resolved_rule_set_version).toBe("1.0.0");
    const started = await gateway.startRun("org-lumi", {
      project_id: "project-summer-launch",
      prompt: "Create one brand-safe direction",
      selected_node_ids: [],
      document_version: 7,
      reference_asset_ids: [],
      reference_artifact_version_ids: [],
      brand_rule_set_version: before.brand_binding?.resolved_rule_set_version ?? null,
    });
    expect(started.run?.brand_rule_set_version).toBe("1.0.0");
  });
});
