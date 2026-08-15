import { DEFAULT_PUBLIC_FEATURE_FLAGS } from "./feature-flags";
import type { PublicFeatureFlagName, PublicFeatureFlags } from "./types";

const ENV_KEYS: Readonly<Record<PublicFeatureFlagName, string>> = {
  projects: "LUMI_FEATURE_PROJECTS",
  brands: "LUMI_FEATURE_BRANDS",
  assets: "LUMI_FEATURE_ASSETS",
  team: "LUMI_FEATURE_TEAM",
  billing: "LUMI_FEATURE_BILLING",
  commandPalette: "LUMI_FEATURE_COMMAND_PALETTE",
};

export function getServerPublicFeatureFlags(env: NodeJS.ProcessEnv = process.env): PublicFeatureFlags {
  const entries = Object.entries(ENV_KEYS).map(([flag, envKey]) => {
    const raw = env[envKey];
    const fallback = DEFAULT_PUBLIC_FEATURE_FLAGS[flag as PublicFeatureFlagName];
    return [flag, raw === undefined ? fallback : raw !== "0" && raw.toLowerCase() !== "false"];
  });
  return Object.freeze(Object.fromEntries(entries)) as PublicFeatureFlags;
}
