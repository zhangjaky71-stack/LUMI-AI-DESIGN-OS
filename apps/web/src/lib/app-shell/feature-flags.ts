import type { PublicFeatureFlags } from "./types";

export const DEFAULT_PUBLIC_FEATURE_FLAGS: PublicFeatureFlags = Object.freeze({
  projects: true,
  brands: true,
  assets: true,
  team: true,
  billing: true,
  commandPalette: true,
});
