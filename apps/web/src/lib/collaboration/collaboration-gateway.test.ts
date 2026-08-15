import { describe, expect, it } from "vitest";
import { DeterministicCollaborationGateway } from "./collaboration-gateway";
import { deterministicCollaborationWorkspace } from "./collaboration-server";

describe("NODE-61 deterministic gateway semantics", () => {
  it("advances canonical version for accepted edits", async () => {
    const gateway = new DeterministicCollaborationGateway(deterministicCollaborationWorkspace("project-summer-launch"));
    const result = await gateway.submitOperations("project-summer-launch", "design-doc-summer-launch", {
      base_version_id: "design-summer-launch-v4",
      operations: [{ operation_id: "op-safe", node_id: "cta", property_name: "fill", value: "#111" }],
    });
    expect(result.conflicts).toHaveLength(0);
    expect(result.canonical_version_after).toBe("design-summer-launch-v5");
  });

  it("preserves the local operation during reconnect conflict", async () => {
    const gateway = new DeterministicCollaborationGateway(deterministicCollaborationWorkspace("project-summer-launch"));
    const result = await gateway.reconnect("project-summer-launch", "design-doc-summer-launch", {
      base_version_id: "design-summer-launch-v4",
      operations: [{ operation_id: "op-local", node_id: "hero-title", property_name: "text", value: "Local edit" }],
    });
    expect(result.rebased).toBe(true);
    expect(result.accepted_operation_ids).toHaveLength(0);
    expect(result.conflicts[0]?.local_operation.value).toBe("Local edit");
  });
});
