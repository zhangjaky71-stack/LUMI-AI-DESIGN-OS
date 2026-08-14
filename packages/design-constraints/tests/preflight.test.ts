import { describe, expect, it } from "vitest";
import type { DesignDocument, DesignOperation } from "../../design-ir/src/index";
import {
  guardedExecute,
  resolveConstraints,
  type ConstraintOverrideToken,
  type DesignConstraint,
} from "../src/index";

function document(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "doc-1",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "root",
        children: ["qr", "headline"],
        transform: { x: 0, y: 0, width: 750, height: 1624 },
      },
      qr: {
        id: "qr",
        kind: "IMAGE",
        parent_id: "frame",
        children: [],
        role: "QR_CODE",
        asset_id: "qr-asset",
        transform: { x: 100, y: 100, width: 180, height: 180, rotation_deg: 0 },
      },
      headline: {
        id: "headline",
        kind: "TEXT",
        parent_id: "frame",
        children: [],
        content: "Hello",
        transform: { x: 100, y: 400, width: 300, height: 80 },
      },
    },
    resources: {},
    metadata: { document_version: 12 },
  };
}

function operation(overrides: Partial<DesignOperation> = {}): DesignOperation {
  return {
    operation_id: "op-1",
    type: "MOVE_NODE",
    target_ids: ["qr"],
    expected_document_version: 12,
    payload: { dx: 20, dy: 0 },
    ...overrides,
  };
}

function constraint(overrides: Partial<DesignConstraint> = {}): DesignConstraint {
  return {
    id: "c-lock",
    type: "LOCK_POSITION",
    scope: { node_ids: ["qr"] },
    severity: "HARD",
    source: "USER_EXPLICIT",
    priority: 1000,
    parameters: {},
    active: true,
    document_version: 12,
    ...overrides,
  };
}

describe("NODE-39 guarded preflight", () => {
  it("denies a hard position lock without returning a candidate document", () => {
    const input = document();
    const before = JSON.stringify(input);
    const result = guardedExecute(input, [operation()], [constraint()]);
    expect(result.preflight.decision).toBe("DENY");
    expect(result.execution).toBeUndefined();
    expect(result.preflight.violations[0]?.reason_code).toBe("CONSTRAINT_POSITION_CHANGED");
    expect(JSON.stringify(input)).toBe(before);
  });

  it("keeps batch atomic when one child violates a hard lock", () => {
    const batch: DesignOperation = operation({
      operation_id: "batch",
      type: "BATCH",
      target_ids: [],
      payload: {
        operations: [
          operation({ operation_id: "move" }),
          operation({
            operation_id: "text",
            type: "SET_TEXT",
            target_ids: ["headline"],
            payload: { content: "Changed" },
          }),
        ],
      },
    });
    const result = guardedExecute(document(), [batch], [constraint()]);
    expect(result.preflight.decision).toBe("DENY");
    expect(result.execution).toBeUndefined();
  });

  it("allows a soft violation while preserving the warning", () => {
    const result = guardedExecute(document(), [operation()], [constraint({ severity: "SOFT" })]);
    expect(result.preflight.decision).toBe("ALLOW_WITH_WARNINGS");
    expect(result.execution?.ok).toBe(true);
  });

  it("requires an exact version-scoped audited override", () => {
    const token: ConstraintOverrideToken = {
      token_id: "override-1",
      constraint_id: "c-lock",
      document_id: "doc-1",
      document_version: 12,
      actor: "user-1",
      reason: "Approved one-time QR reposition",
      one_time: true,
    };
    const result = guardedExecute(document(), [operation()], [constraint()], { overrides: [token] });
    expect(result.preflight.decision).toBe("ALLOW");
    expect(result.execution?.ok).toBe(true);
  });

  it("fails closed on a stale hard constraint snapshot", () => {
    const result = guardedExecute(document(), [operation()], [constraint({ document_version: 11 })]);
    expect(result.preflight.decision).toBe("DENY");
    expect(result.preflight.violations[0]?.reason_code).toBe("STALE_CONSTRAINT_SNAPSHOT");
  });

  it("surfaces equal-precedence incompatible constraints as a conflict", () => {
    const constraints = [
      constraint({ id: "a", type: "MIN_MARGIN", parameters: { container_id: "frame", min_px: 24 } }),
      constraint({ id: "b", type: "MIN_MARGIN", parameters: { container_id: "frame", min_px: 48 } }),
    ];
    const resolved = resolveConstraints(document(), constraints);
    expect(resolved.conflicts).toHaveLength(1);
    expect(resolved.constraints).toHaveLength(0);
  });

  it("uses source precedence before lower-priority inferred rules", () => {
    const constraints = [
      constraint({ id: "user", parameters: { marker: "user" }, source: "USER_EXPLICIT", priority: 10 }),
      constraint({ id: "agent", parameters: { marker: "agent" }, source: "AGENT_INFERRED", priority: 9999 }),
    ];
    const resolved = resolveConstraints(document(), constraints);
    expect(resolved.constraints.map((item) => item.id)).toEqual(["user"]);
  });
});
