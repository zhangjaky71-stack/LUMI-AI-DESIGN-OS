import { describe, expect, it } from "vitest";
import { DeterministicBrandKitGateway } from "./brand-kit-gateway";
import { getBrandKitBootstrap } from "./brand-kit-server";

function seed() {
  const previous = process.env.LUMI_BRAND_KIT_E2E;
  process.env.LUMI_BRAND_KIT_E2E = "1";
  const bootstrap = getBrandKitBootstrap();
  if (previous === undefined) delete process.env.LUMI_BRAND_KIT_E2E;
  else process.env.LUMI_BRAND_KIT_E2E = previous;
  if (!bootstrap.seed) throw new Error("test seed missing");
  return structuredClone(bootstrap.seed);
}

describe("Deterministic Brand Kit gateway", () => {
  it("publishes an immutable new BrandRuleSet and advances CURRENT project bindings", async () => {
    const gateway = new DeterministicBrandKitGateway(seed());
    const before = await gateway.getBrandKit("org-lumi");
    const next = await gateway.publishDraft("org-lumi", {
      brand_profile_id: before.detail.profile.id,
      expected_draft_revision: before.detail.draft_revision,
    });
    expect(next.detail.published_versions.map((item) => item.version)).toEqual(["1.0.0", "2.0.0"]);
    expect(next.detail.published_versions[0]?.status).toBe("PUBLISHED");
    expect(next.detail.draft_rule_set.version).toBe("3.0.0-draft");
    expect(next.detail.project_bindings.find((item) => item.project_id === "project-summer-launch")?.resolved_rule_set_version).toBe("2.0.0");
    expect(next.detail.project_bindings.find((item) => item.project_id === "project-store-signage")?.resolved_rule_set_version).toBe("1.0.0");
  });

  it("requires cited human review before Brand Guide candidates become approved rules", async () => {
    const gateway = new DeterministicBrandKitGateway(seed());
    const file = new File(["brand guide"], "brand-guide.pdf", { type: "application/pdf" });
    const imported = await gateway.uploadAsset("org-lumi", {
      brand_profile_id: "brand-lumi-coffee",
      file,
      kind: "GUIDE",
      rights_assertion: "USER_OWNED",
    });
    const proposal = imported.detail.guide_proposals[0];
    expect(proposal?.status).toBe("PROPOSED");
    expect(proposal?.candidates.every((candidate) => candidate.citations.length > 0)).toBe(true);
    expect(proposal?.candidates.some((candidate) => candidate.rule.severity === "HARD")).toBe(false);
    if (!proposal) throw new Error("proposal missing");

    const reviewed = await gateway.reviewGuideProposal("org-lumi", {
      brand_profile_id: "brand-lumi-coffee",
      proposal_id: proposal.id,
      expected_draft_revision: imported.detail.draft_revision,
      decisions: proposal.candidates.map((candidate, index) => ({
        candidate_id: candidate.candidate_id,
        decision: index === 0 ? "APPROVE" as const : "REJECT" as const,
        ...(index === 0 ? { severity: "HARD" as const } : {}),
      })),
    });
    const approved = reviewed.detail.draft_rule_set.rules.find((rule) => rule.source === "APPROVED_GUIDE_EXTRACTION");
    expect(approved?.severity).toBe("HARD");
    expect(approved?.citations?.length).toBeGreaterThan(0);
  });

  it("blocks unknown font rights and stale compliance versions", async () => {
    const gateway = new DeterministicBrandKitGateway(seed());
    const uploaded = await gateway.uploadAsset("org-lumi", {
      brand_profile_id: "brand-lumi-coffee",
      file: new File(["font"], "UnknownBrand.woff2", { type: "font/woff2" }),
      kind: "FONT",
      rights_assertion: "UNKNOWN",
    });
    await expect(gateway.publishDraft("org-lumi", {
      brand_profile_id: "brand-lumi-coffee",
      expected_draft_revision: uploaded.detail.draft_revision,
    })).rejects.toThrow(/PUBLISH_BLOCKED/);

    await expect(gateway.checkCompliance("org-lumi", {
      brand_profile_id: "brand-lumi-coffee",
      artifact_version_id: "artifact-version-brand-check-1",
      brand_rule_set_version: "0.0.0-stale",
    })).rejects.toThrow(/BRAND_RULE_VERSION_STALE/);
  });
});
