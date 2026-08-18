import { BrandStudio } from "@/components/brands/brand-studio";
import { requireAppSession } from "@/lib/auth/session";
import { getActiveBrandRuleSet, getBrand, getGuideProposal, listBrands } from "@/lib/brands/server";
import { listProjects } from "@/lib/projects/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  brand?: string | string[];
  proposal?: string | string[];
}>;

export default async function BrandKitPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const requestedBrandId = scalar(params.brand);
  const proposalId = scalar(params.proposal);
  const [session, brands, projects] = await Promise.all([
    requireAppSession(),
    listBrands(),
    listProjects(),
  ]);
  const selectedBrandId = requestedBrandId ?? brands[0]?.id ?? null;
  const selectedBrand = selectedBrandId ? await getBrand(selectedBrandId) : null;
  const activeRuleSet = selectedBrandId ? await getActiveBrandRuleSet(selectedBrandId) : null;
  const proposal = selectedBrandId && proposalId
    ? await getGuideProposal(selectedBrandId, proposalId)
    : null;

  return (
    <BrandStudio
      organizationId={session.organization.id}
      initialBrands={brands}
      selectedBrand={selectedBrand}
      activeRuleSet={activeRuleSet}
      initialProposal={proposal}
      initialProjects={projects}
    />
  );
}

function scalar(value: string | string[] | undefined): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}
