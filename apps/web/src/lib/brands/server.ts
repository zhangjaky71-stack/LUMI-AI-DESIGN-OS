import { ApiError } from "@/lib/api/problem";
import { serverApiRequest } from "@/lib/api/server";
import { requireAppSession } from "@/lib/auth/session";
import {
  parseBrandPage,
  parseBrandRecord,
  parseBrandRuleSet,
  parseGuideProposal,
  type BrandGuideProposal,
  type BrandRecord,
  type BrandRuleSet,
} from "@/lib/brands/types";

const BRANDS_PATH = "/api/v1/brands";

export async function listBrands(): Promise<readonly BrandRecord[]> {
  const payload = await serverApiRequest<unknown>(BRANDS_PATH, {
    method: "GET",
    headers: await tenantHeaders(),
  });
  return parseBrandPage(payload);
}

export async function getBrand(brandId: string): Promise<BrandRecord> {
  const payload = await serverApiRequest<unknown>(brandPath(brandId), {
    method: "GET",
    headers: await tenantHeaders(),
  });
  return parseBrandRecord(payload);
}

export async function getActiveBrandRuleSet(brandId: string): Promise<BrandRuleSet | null> {
  try {
    const payload = await serverApiRequest<unknown>(`${brandPath(brandId)}/rule-sets/active`, {
      method: "GET",
      headers: await tenantHeaders(),
    });
    return parseBrandRuleSet(payload);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function getBrandRuleSet(brandId: string, ruleSetId: string): Promise<BrandRuleSet> {
  const payload = await serverApiRequest<unknown>(`${brandPath(brandId)}/rule-sets/${encodeURIComponent(ruleSetId)}`, {
    method: "GET",
    headers: await tenantHeaders(),
  });
  return parseBrandRuleSet(payload);
}

export async function getGuideProposal(brandId: string, proposalId: string): Promise<BrandGuideProposal> {
  const payload = await serverApiRequest<unknown>(`${brandPath(brandId)}/guide-proposals/${encodeURIComponent(proposalId)}`, {
    method: "GET",
    headers: await tenantHeaders(),
  });
  return parseGuideProposal(payload);
}

export function brandPath(brandId: string): string {
  const id = brandId.trim();
  if (!id) throw new Error("BRAND_ID_REQUIRED");
  return `${BRANDS_PATH}/${encodeURIComponent(id)}`;
}

async function tenantHeaders(): Promise<Record<string, string>> {
  const session = await requireAppSession();
  return { "X-Organization-ID": session.organization.id };
}
