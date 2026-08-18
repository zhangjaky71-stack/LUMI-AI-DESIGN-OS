import { describe, expect, it } from "vitest";

import { parseCommentThreadBundles } from "@/lib/collaboration/types";

const ORG = "0198a1b2-c3d4-7e5f-8123-123456789abc";
const PROJECT = "0198a1b2-c3d4-7e5f-8123-123456789abd";
const ARTIFACT = "0198a1b2-c3d4-7e5f-8123-123456789abe";
const VERSION = "0198a1b2-c3d4-7e5f-8123-123456789abf";
const OLD_VERSION = "0198a1b2-c3d4-7e5f-8123-123456789ac0";
const THREAD = "0198a1b2-c3d4-7e5f-8123-123456789ac1";
const COMMENT = "0198a1b2-c3d4-7e5f-8123-123456789ac2";

function bundle(version = VERSION, needsReanchor = false) {
  return {
    thread: {
      id: THREAD,
      organization_id: ORG,
      project_id: PROJECT,
      artifact_id: ARTIFACT,
      artifact_version_id: version,
      design_node_id: null,
      x: null,
      y: null,
      status: "OPEN",
      needs_reanchor: needsReanchor,
      created_by: ORG,
      created_at: "2026-08-18T05:00:00Z",
      resolved_by: null,
      resolved_at: null,
    },
    comments: [{
      id: COMMENT,
      organization_id: ORG,
      thread_id: THREAD,
      body: "Review this exact version",
      mention_user_ids: [],
      created_by: ORG,
      revision: 1,
      created_at: "2026-08-18T05:00:00Z",
      edited_at: null,
      deleted_at: null,
    }],
  };
}

describe("NODE-61 collaboration web contracts", () => {
  it("preserves exact artifact-version binding", () => {
    const [value] = parseCommentThreadBundles([bundle()]);
    expect(value?.thread.artifactVersionId).toBe(VERSION);
    expect(value?.comments[0]?.body).toBe("Review this exact version");
  });

  it("preserves historical re-anchor state without rewriting the version id", () => {
    const [value] = parseCommentThreadBundles([bundle(OLD_VERSION, true)]);
    expect(value?.thread.artifactVersionId).toBe(OLD_VERSION);
    expect(value?.thread.needsReanchor).toBe(true);
  });

  it("preserves deleted placeholder and revision", () => {
    const payload = bundle();
    payload.comments[0] = {
      ...payload.comments[0],
      body: "[deleted]",
      revision: 3,
      deleted_at: "2026-08-18T05:10:00Z",
    };
    const [value] = parseCommentThreadBundles([payload]);
    expect(value?.comments[0]?.body).toBe("[deleted]");
    expect(value?.comments[0]?.revision).toBe(3);
    expect(value?.comments[0]?.deletedAt).toBe("2026-08-18T05:10:00Z");
  });

  it("rejects unknown thread status", () => {
    const payload = bundle();
    payload.thread.status = "APPROVED";
    expect(() => parseCommentThreadBundles([payload])).toThrow("COLLABORATION_THREAD_STATUS_INVALID");
  });
});
