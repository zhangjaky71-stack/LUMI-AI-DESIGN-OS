import { describe, expect, it } from "vitest";
import { ArtifactEngine } from "../../artifact-sdk/src/engine";
import type { Artifact, ArtifactBranch, ArtifactVersion } from "../../artifact-sdk/src/types";
import { ArtifactEngineQualityAdapter, InMemoryQualityResultRepository } from "./artifact-adapter";
import { QualityEngine } from "./engine";
import type { QualityProfile } from "./types";

const ORG = "00000000-0000-4000-8000-000000000001";
const PROJECT = "00000000-0000-4000-8000-000000000002";
const ARTIFACT = "00000000-0000-4000-8000-000000000003";
const VERSION = "00000000-0000-4000-8000-000000000004";
const DESIGN = "00000000-0000-4000-8000-000000000005";
const BRANCH = "00000000-0000-4000-8000-000000000006";
const HASH = "a".repeat(64);

function seeded(): ArtifactEngine {
  const engine = new ArtifactEngine();
  const artifact: Artifact = { id: ARTIFACT, organization_id: ORG, project_id: PROJECT, type: "DESIGN_DOCUMENT", title: "Quality fixture", archived: false };
  const branch: ArtifactBranch = { id: BRANCH, organization_id: ORG, artifact_id: ARTIFACT, name: "main", base_version_id: null, head_version_id: null, created_by: "user-1" };
  const version: ArtifactVersion = { id: VERSION, organization_id: ORG, artifact_id: ARTIFACT, branch_id: BRANCH, parent_version_id: null, schema_version: "1.0", version_number: 1, status: "READY", content_hash: HASH, constraint_snapshot_hash: HASH, created_by_type: "SYSTEM", created_by_id: "fixture", created_at: "2026-08-15T00:00:00.000Z", design_document_version_id: DESIGN };
  engine.addArtifact(artifact);
  engine.addBranch(branch);
  engine.addVersion(version, null);
  return engine;
}

const resolutionProfile: QualityProfile = {
  profile_id: "quality:test-resolution",
  version: "1.0.0",
  name: "production-web",
  overall_pass_threshold: 90,
  overall_warning_threshold: 80,
  review_confidence_threshold: 0.9,
  dimensions: [{ dimension: "RESOLUTION_EXPORT_READINESS", weight: 1, threshold: 90, hard_gate: true, minimum_confidence: 0.9 }],
};

describe("NODE-50 Artifact QualityResult integration", () => {
  it("persists full result and appends only normalized quality metadata to exact ArtifactVersion", async () => {
    const artifacts = seeded();
    const original = structuredClone(artifacts.versions.get(VERSION)!);
    const results = new InMemoryQualityResultRepository();
    const adapter = new ArtifactEngineQualityAdapter({ artifacts, results });
    const critic = new QualityEngine({ ports: { artifact: adapter }, now: () => "2026-08-15T00:01:00.000Z" });
    const result = await critic.evaluate({
      profile: resolutionProfile,
      subject: {
        organization_id: ORG,
        project_id: PROJECT,
        artifact_id: ARTIFACT,
        artifact_version_id: VERSION,
        design_document_version_id: DESIGN,
        rendered_asset_ref: "preview:1",
        width: 1600,
        height: 1200,
        metadata: { minimum_export_width: 1200, minimum_export_height: 900 },
        design_document: {
          schema_version: "1.0",
          document_id: "doc-1",
          unit: "px",
          root_id: "root",
          nodes: { root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: [] } },
          resources: {},
          metadata: { document_version: 1 },
        },
      },
    });
    expect(result.status).toBe("PASS");
    expect((await results.get(ORG, result.quality_result_id))?.overall_score).toBe(100);
    const updated = artifacts.versions.get(VERSION)!;
    expect(updated.quality_score).toBe(1);
    expect(updated.content_hash).toBe(original.content_hash);
    expect(updated.status).toBe(original.status);
    expect(artifacts.branches.get(BRANCH)?.head_version_id).toBe(VERSION);
  });

  it("rejects cross-project attachment instead of leaking quality metadata", async () => {
    const artifacts = seeded();
    const results = new InMemoryQualityResultRepository();
    const adapter = new ArtifactEngineQualityAdapter({ artifacts, results });
    await expect(adapter.record({
      quality_result_id: "quality-result:x",
      organization_id: ORG,
      project_id: "00000000-0000-4000-8000-000000000099",
      artifact_id: ARTIFACT,
      artifact_version_id: VERSION,
      design_document_version_id: DESIGN,
      profile_id: "p",
      profile_version: "1",
      status: "PASS",
      overall_score: 100,
      confidence: 1,
      dimensions: [],
      violations: [],
      strengths: [],
      repair_actions: [],
      evidence: [],
      unavailable_graders: [],
      grader_versions: {},
      created_at: "2026-08-15T00:00:00.000Z",
    })).rejects.toThrow("QUALITY_ARTIFACT_SCOPE_MISMATCH");
  });
});
