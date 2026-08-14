import { canonicalSha256 } from "../../design-ir/src/index";
import type { IdentityReferenceSet, ThresholdCalibrationProfile } from "./types";

export interface IdentityCacheKeyInput {
  readonly candidate_checksum_sha256: string;
  readonly identity: IdentityReferenceSet;
  readonly profile: ThresholdCalibrationProfile;
  readonly provider_id: string;
  readonly provider_version: string;
  readonly preprocessor_version: string;
}

export async function identityCacheKey(input: IdentityCacheKeyInput): Promise<string> {
  const digest = await canonicalSha256({
    candidate_checksum_sha256: input.candidate_checksum_sha256,
    identity_id: input.identity.identity_id,
    reference_set_version: input.identity.version,
    threshold_profile_id: input.profile.profile_id,
    threshold_profile_version: input.profile.version,
    calibration_dataset_version: input.profile.calibration_dataset_version,
    provider_id: input.provider_id,
    provider_version: input.provider_version,
    preprocessor_version: input.preprocessor_version,
  });
  return `identity-cache:${digest}`;
}

export class IdentityValidationCache<T> {
  readonly #entries = new Map<string, T>();

  get(key: string): T | undefined {
    return this.#entries.get(key);
  }

  set(key: string, value: T): void {
    this.#entries.set(key, value);
  }

  clear(): void {
    this.#entries.clear();
  }
}
