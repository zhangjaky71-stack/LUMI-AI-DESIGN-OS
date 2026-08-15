import { describe, expect, it } from "vitest";
import {
  anchorLabel,
  assertExactCollaborationVersion,
  canComment,
  canEdit,
  operationConflictKey,
  validateCommentBody,
} from "./contracts";
import type { CollaborationThread } from "./types";

const thread: CollaborationThread = {
  thread_id: "thread-old",
  anchor: {
    project_id: "project-a",
    artifact_version_id: "artifact-v2",
    design_document_version_id: "design-v2",
    node_id: "deleted-node",
    frame_id: null,
    historical: true,
  },
  status: "OPEN",
  messages: [],
  created_at: "2026-08-15T06:30:00.000Z",
};

describe("NODE-61 collaboration contracts", () => {
  it("rejects floating version anchors", () => {
    expect(() => assertExactCollaborationVersion("latest", "design_version")).toThrow(/MUST_BE_EXACT/);
    expect(() => assertExactCollaborationVersion("design-v4", "design_version")).not.toThrow();
  });

  it("uses canonical NODE-16 roles instead of a parallel client role", () => {
    expect(canComment("VIEWER")).toBe(true);
    expect(canComment("ADMIN")).toBe(true);
    expect(canComment("BILLING")).toBe(false);
    expect(canEdit("VIEWER")).toBe(false);
    expect(canEdit("EDITOR")).toBe(true);
    expect(canEdit("ADMIN")).toBe(true);
  });

  it("renders exact historical context", () => {
    expect(anchorLabel(thread, "design-v4")).toContain("design-v2");
    expect(anchorLabel(thread, "design-v4")).toContain("Historical");
  });

  it("validates comments and stable property conflict keys", () => {
    expect(validateCommentBody("  review this  ")).toBe("review this");
    expect(() => validateCommentBody("   ")).toThrow(/EMPTY/);
    expect(operationConflictKey({ operation_id: "op-1", node_id: "hero", property_name: "text", value: "x" })).toBe("hero::text");
  });
});
