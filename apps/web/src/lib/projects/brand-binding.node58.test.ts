import { describe, expect, it } from "vitest";

import { parseProjectSummary } from "./types";

describe("NODE-58 project brand binding contract", () => {
  it("preserves canonical resource version and brand_id for If-Match binding", () => {
    const project = parseProjectSummary({
      id: "project-1",
      name: "Launch",
      status: "ACTIVE",
      version: 9,
      workspace_id: "workspace-1",
      brand_id: "brand-1",
      created_at: "2026-08-18T00:00:00Z",
      updated_at: "2026-08-18T00:10:00Z",
    });
    expect(project.version).toBe(9);
    expect(project.brandId).toBe("brand-1");
    expect(project.workspaceId).toBe("workspace-1");
  });
});
