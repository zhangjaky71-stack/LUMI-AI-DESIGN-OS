import type {
  BrandGuideExtractionCandidate,
  BrandGuideExtractionProposal,
  BrandRule,
  BrandRuleSeverity,
} from "./types";
import { BrandRuleError } from "./runtime";

export function createExtractionProposal(input: Omit<BrandGuideExtractionProposal, "status" | "candidates"> & {
  readonly candidates: readonly BrandGuideExtractionCandidate[];
}): BrandGuideExtractionProposal {
  const candidates = input.candidates.map((candidate) => {
    if (candidate.confidence < 0 || candidate.confidence > 1) throw new BrandRuleError("extraction confidence must be in [0,1]");
    if (!candidate.citations.length) throw new BrandRuleError(`candidate ${candidate.candidate_id} requires source citations`);
    if (candidate.rule.severity === "HARD") throw new BrandRuleError("unreviewed extraction cannot propose a HARD rule");
    return {
      ...candidate,
      rule: { ...candidate.rule, source: "INFERRED_PROPOSAL" as const, citations: [...candidate.citations] },
    };
  });
  return { ...input, status: "PROPOSED", candidates };
}

export interface ApprovedCandidate {
  readonly candidate_id: string;
  readonly severity?: BrandRuleSeverity;
  readonly priority?: number;
}

export interface ExtractionApprovalResult {
  readonly proposal: BrandGuideExtractionProposal;
  readonly approved_rules: readonly BrandRule[];
}

export function approveExtractionProposal(
  proposal: BrandGuideExtractionProposal,
  approvals: readonly ApprovedCandidate[],
  reviewer: string,
  reviewedAt: string,
): ExtractionApprovalResult {
  if (proposal.status !== "PROPOSED") throw new BrandRuleError("only PROPOSED extraction can be approved");
  if (!reviewer) throw new BrandRuleError("extraction approval requires reviewer identity");
  const approvalMap = new Map(approvals.map((item) => [item.candidate_id, item]));
  const approvedRules: BrandRule[] = [];
  for (const candidate of proposal.candidates) {
    const approval = approvalMap.get(candidate.candidate_id);
    if (!approval) continue;
    if (!candidate.citations.length) throw new BrandRuleError(`candidate ${candidate.candidate_id} cannot be approved without citations`);
    approvedRules.push({
      ...candidate.rule,
      severity: approval.severity ?? candidate.rule.severity,
      priority: approval.priority ?? candidate.rule.priority,
      source: "APPROVED_GUIDE_EXTRACTION",
      citations: [...candidate.citations],
    });
  }
  if (!approvedRules.length) throw new BrandRuleError("approval must select at least one extraction candidate");
  return {
    proposal: { ...proposal, status: "APPROVED", reviewed_by: reviewer, reviewed_at: reviewedAt },
    approved_rules: approvedRules.sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id)),
  };
}

export function rejectExtractionProposal(
  proposal: BrandGuideExtractionProposal,
  reviewer: string,
  reviewedAt: string,
): BrandGuideExtractionProposal {
  if (proposal.status !== "PROPOSED") throw new BrandRuleError("only PROPOSED extraction can be rejected");
  if (!reviewer) throw new BrandRuleError("extraction rejection requires reviewer identity");
  return { ...proposal, status: "REJECTED", reviewed_by: reviewer, reviewed_at: reviewedAt };
}
