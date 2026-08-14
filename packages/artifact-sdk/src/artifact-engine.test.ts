import { describe, expect, it } from "vitest";
import { ArtifactBranchConflictError, ArtifactEngine } from "./engine";
import { artifactManifestSha256 } from "./hashing";
import { liveArtifactStorageKeys } from "./gc";
import type { Artifact, ArtifactBranch, ArtifactFile, ArtifactProvenance, ArtifactVersion } from "./types";

const H = "a".repeat(64);
const C = "b".repeat(64);
const GIT = "c".repeat(40);
const artifact: Artifact = { id: "a1", organization_id: "o1", project_id: "p1", type: "DESIGN_DOCUMENT", title: "LUMI", archived: false };
const branch: ArtifactBranch = { id: "b1", organization_id: "o1", artifact_id: "a1", name: "main", base_version_id: null, head_version_id: null, created_by: "u1" };
function version(id: string, number: number, parent: string | null = null): ArtifactVersion {
  return { id, organization_id: "o1", artifact_id: "a1", branch_id: "b1", parent_version_id: parent, schema_version: "1.0", version_number: number, status: "DRAFT", content_hash: H, constraint_snapshot_hash: C, created_by_type: "USER", created_by_id: "u1", created_at: `2026-08-14T00:00:0${number}Z` };
}
function seeded() { const engine = new ArtifactEngine(); engine.addArtifact(artifact); engine.addBranch(branch); return engine; }

describe("NODE-42 Artifact Engine", () => {
  it("enforces branch CAS and monotonic version identity", () => {
    const engine = seeded();
    engine.addVersion(version("v1", 1), null);
    expect(engine.branches.get("b1")?.head_version_id).toBe("v1");
    expect(() => engine.addVersion(version("v2", 2, "v1"), null)).toThrow(ArtifactBranchConflictError);
    engine.addVersion(version("v2", 2, "v1"), "v1");
    expect(engine.nextVersionNumber("a1")).toBe(3);
  });

  it("restores by appending a new version and lineage edge", () => {
    const engine = seeded();
    engine.addVersion(version("v1", 1), null);
    engine.addVersion({ ...version("v2", 2, "v1"), content_hash: "d".repeat(64) }, "v1");
    const restored = engine.restore("v1", "b1", { id: "v3", version_number: 3, constraint_snapshot_hash: C, created_by_type: "USER", created_by_id: "u1", created_at: "2026-08-14T00:00:03Z" }, "e1");
    expect(restored.content_hash).toBe(H);
    expect(restored.parent_version_id).toBe("v2");
    expect(engine.versions.get("v1")?.content_hash).toBe(H);
    expect(engine.edges.get("e1")?.metadata).toEqual({ operation: "RESTORE" });
  });

  it("requires validated READY before approval and preserves immutable content", () => {
    const engine = seeded(); engine.addVersion(version("v1", 1), null);
    engine.transition("v1", "READY");
    expect(() => engine.transition("v1", "APPROVED", false)).toThrow();
    const approved = engine.transition("v1", "APPROVED", true, 0.98);
    expect(approved.content_hash).toBe(H);
    expect(approved.status).toBe("APPROVED");
  });

  it("attaches a file only after storage HEAD/checksum/size/MIME verification", async () => {
    const engine = seeded(); engine.addVersion(version("v1", 1), null);
    const file: ArtifactFile = { id: "f1", organization_id: "o1", artifact_version_id: "v1", role: "PREVIEW", storage_key: "org/o1/artifacts/x.png", mime_type: "image/png", size_bytes: 10, checksum_sha256: H };
    await expect(engine.attachVerifiedFile(file, { stat: async () => null })).rejects.toThrow("missing");
    await expect(engine.attachVerifiedFile(file, { stat: async () => ({ storage_key: file.storage_key, size_bytes: 10, checksum_sha256: C, mime_type: "image/png" }) })).rejects.toThrow("checksum");
    await engine.attachVerifiedFile(file, { stat: async () => ({ storage_key: file.storage_key, size_bytes: 10, checksum_sha256: H, mime_type: "image/png" }) });
    expect(engine.files.has("f1")).toBe(true);
  });

  it("keeps stable manifest hash independent from runtime signed URLs", async () => {
    const v = version("v1", 1);
    const base: ArtifactProvenance = { artifact_version_id: "v1", organization_id: "o1", constraint_snapshot_hash: C, code_git_sha: GIT, compiler: { compiler_version: "1.0.0", document_id: "d1", schema_version: "1.0", document_version: 4, resource_versions: { asset: "7" }, font_versions: { Inter: "4" }, compile_hash: H } };
    const file: ArtifactFile = { id: "f1", organization_id: "o1", artifact_version_id: "v1", role: "PREVIEW", storage_key: "org/o1/hash.png", mime_type: "image/png", size_bytes: 10, checksum_sha256: H, metadata: { signed_url: "https://one" } };
    const first = await artifactManifestSha256(v, base, [file]);
    const second = await artifactManifestSha256(v, base, [{ ...file, metadata: { signed_url: "https://two" } }]);
    expect(first).toBe(second);
  });

  it("protects branch heads and approved versions from GC", () => {
    const files: ArtifactFile[] = [{ id: "f1", organization_id: "o1", artifact_version_id: "v1", role: "PREVIEW", storage_key: "blob1", mime_type: "image/png", size_bytes: 10, checksum_sha256: H }];
    expect(liveArtifactStorageKeys([{ ...version("v1", 1), status: "APPROVED" }], [{ ...branch, head_version_id: "v1" }], files).has("blob1")).toBe(true);
  });
});
