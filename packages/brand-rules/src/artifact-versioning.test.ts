import { describe, expect, it } from "vitest";
import { artifactManifestSha256 } from "../../artifact-sdk/src/hashing";
import type { ArtifactProvenance, ArtifactVersion } from "../../artifact-sdk/src/types";

const version: ArtifactVersion = {
  id: "v1",
  organization_id: "org",
  artifact_id: "artifact",
  branch_id: "branch",
  parent_version_id: null,
  schema_version: "1.0",
  version_number: 1,
  status: "READY",
  content_hash: "a".repeat(64),
  constraint_snapshot_hash: "b".repeat(64),
  created_by_type: "SYSTEM",
  created_by_id: "system",
  created_at: "2026-08-14T00:00:00Z",
};

const provenance: ArtifactProvenance = {
  artifact_version_id: "v1",
  organization_id: "org",
  constraint_snapshot_hash: "b".repeat(64),
  code_git_sha: "c".repeat(40),
};

describe("NODE-43 artifact brand-version provenance", () => {
  it("keeps legacy manifest identity when no brand rule version exists", async () => {
    const first = await artifactManifestSha256(version, provenance, []);
    const second = await artifactManifestSha256({ ...version, brand_rule_set_version: null }, provenance, []);
    expect(first).toBe(second);
  });

  it("binds a concrete brand rule version into the stable manifest", async () => {
    const legacy = await artifactManifestSha256(version, provenance, []);
    const branded = await artifactManifestSha256(
      { ...version, brand_rule_set_version: "1.0.0" },
      { ...provenance, brand_rule_set_version: "1.0.0" },
      [],
    );
    expect(branded).not.toBe(legacy);
  });

  it("rejects version/provenance brand version disagreement", async () => {
    await expect(artifactManifestSha256(
      { ...version, brand_rule_set_version: "1.0.0" },
      { ...provenance, brand_rule_set_version: "2.0.0" },
      [],
    )).rejects.toThrow(/brand rule set version mismatch/);
  });
});
