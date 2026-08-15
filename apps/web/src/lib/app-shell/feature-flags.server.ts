import { DEFAULT_PUBLIC_FEATURE_FLAGS } from "./feature-flags";
import {
  PUBLIC_FEATURE_FLAG_NAMES,
  type PublicFeatureFlagName,
  type PublicFeatureFlags,
} from "./types";

const ENV_KEYS: Readonly<Record<PublicFeatureFlagName, string>> = {
  projects: "LUMI_FEATURE_PROJECTS",
  brands: "LUMI_FEATURE_BRANDS",
  assets: "LUMI_FEATURE_ASSETS",
  team: "LUMI_FEATURE_TEAM",
  billing: "LUMI_FEATURE_BILLING",
  commandPalette: "LUMI_FEATURE_COMMAND_PALETTE",
};

export function getServerPublicFeatureFlags(
  env: NodeJS.ProcessEnv = process.env,
): PublicFeatureFlags {
  const entries = PUBLIC_FEATURE_FLAG_NAMES.map((flag) => {
    const raw = env[ENV_KEYS[flag]];
    const fallback = DEFAULT_PUBLIC_FEATURE_FLAGS[flag];
    const enabled =
      raw === undefined
        ? fallback
        : raw !== "0" && raw.toLowerCase() !== "false";
    return [flag, enabled] as const;
  });

  return Object.freeze(Object.fromEntries(entries)) as PublicFeatureFlags;
}
