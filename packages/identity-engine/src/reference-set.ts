import { assertReferencePrivacy, DEFAULT_IDENTITY_PRIVACY_POLICY } from "./privacy";
import type {
  IdentityPrivacyPolicy,
  IdentityReferenceSet,
  ThresholdCalibrationProfile,
  VerifiedIdentityAsset,
} from "./types";

export interface CreateIdentityReferenceSetInput extends Omit<IdentityReferenceSet, "status"> {
  readonly status?: IdentityReferenceSet["status"];
}

export function createIdentityReferenceSet(
  input: CreateIdentityReferenceSetInput,
  references: readonly VerifiedIdentityAsset[],
  profile: ThresholdCalibrationProfile,
  privacyPolicy: IdentityPrivacyPolicy = DEFAULT_IDENTITY_PRIVACY_POLICY,
): IdentityReferenceSet {
  if (!input.identity_id.trim() || !input.version.trim()) throw new Error("IDENTITY_REFERENCE_ID_VERSION_REQUIRED");
  if (input.organization_id !== profile.organization_id) throw new Error("IDENTITY_PROFILE_TENANT_MISMATCH");
  if (input.type !== profile.identity_type) throw new Error("IDENTITY_PROFILE_TYPE_MISMATCH");
  if (input.threshold_profile_id !== profile.profile_id || input.threshold_profile_version !== profile.version) {
    throw new Error("IDENTITY_PROFILE_VERSION_MISMATCH");
  }
  const status = input.status ?? "DRAFT";
  if (status === "PUBLISHED" && profile.status !== "PUBLISHED") throw new Error("IDENTITY_THRESHOLD_PROFILE_NOT_PUBLISHED");
  if (!input.canonical_asset_ids.length || !input.reference_views.length) throw new Error("IDENTITY_REFERENCE_SET_EMPTY");

  const byKey = new Map(references.map((asset) => [`${asset.asset_id}@${asset.asset_version}`, asset]));
  const canonical = new Set(input.canonical_asset_ids);
  for (const view of input.reference_views) {
    if (view.organization_id !== input.organization_id) throw new Error("IDENTITY_REFERENCE_TENANT_MISMATCH");
    const asset = byKey.get(`${view.asset_id}@${view.asset_version}`);
    if (!asset || asset.organization_id !== input.organization_id) throw new Error("IDENTITY_REFERENCE_ASSET_NOT_READY");
  }
  for (const assetId of canonical) {
    if (!references.some((asset) => asset.asset_id === assetId && asset.organization_id === input.organization_id)) {
      throw new Error(`IDENTITY_CANONICAL_ASSET_UNRESOLVED:${assetId}`);
    }
  }

  const result: IdentityReferenceSet = {
    ...input,
    canonical_asset_ids: [...canonical].sort(),
    reference_views: [...input.reference_views].sort((a, b) => a.view_id.localeCompare(b.view_id)),
    status,
  };
  if (status === "PUBLISHED") assertReferencePrivacy(result, privacyPolicy);
  return result;
}
